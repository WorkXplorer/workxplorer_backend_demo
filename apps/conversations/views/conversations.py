from rest_framework import generics
from rest_framework.views import APIView
from django.db.models import Prefetch, Q, Max
from django.db.models.functions import Coalesce

from core.responses import APIResponse

from apps.conversations.models import Conversation, Message
from apps.conversations.serializers.conversations import (
    ConversationListSerializer,
    ConversationDetailSerializer,
)
from apps.applications.models import ApplicationDocument
from apps.resumes.models import Resume
from utils.candidate_permission import (
    IsCandidatePermission,
    IsCandidateOrRecruiterPermission,
)
from utils.recruiter_permission import IsRecruiterPermission
from apps.profiles.models import RecruiterProfile
from django.utils.translation import gettext as _


class RecruiterConversationListView(generics.ListAPIView):
    """
    List all conversations for the authenticated recruiter.
    
    Shows all candidates who have applied to vacancies created by this recruiter.
    Each conversation contains the cover letter from the candidate's application.
    """

    serializer_class = ConversationListSerializer
    permission_classes = [IsRecruiterPermission]

    def get_queryset(self):
        """
        Return conversations where the authenticated recruiter is a participant.
        Optimized with select_related and prefetch_related to avoid N+1 queries.
        """
        user = self.request.user
        search = self.request.query_params.get('search', '').strip()

        # Import CompanyProfile for prefetch optimization
        from apps.profiles.models import CompanyProfile

        queryset = (
            Conversation.objects
            .filter(recruiter_id=user.id)
            .select_related(
                "candidate",
                "candidate__candidateprofile",
                "recruiter",
                "recruiter__company",
                "application",
                "application__vacancy",
                "vacancy",  # For headhunting conversations
            )
            .prefetch_related(
                Prefetch(
                    "messages",
                    queryset=Message.objects.order_by("-created_at")[:1],
                    to_attr="recent_messages",
                ),
                Prefetch(
                    "recruiter__recruiterprofile_set",
                    queryset=RecruiterProfile.objects.only(
                        "id", "recruiter_id", "full_name", "photo"
                    ),
                ),
                Prefetch(
                    "recruiter__company__companyprofile",
                    queryset=CompanyProfile.objects.only(
                        "id", "company_id", "photo"
                    ),
                    to_attr="prefetched_company_profile",
                ),
                Prefetch(
                    "candidate__resumes",
                    queryset=Resume.objects.filter(
                        is_active=True
                    ).only("id", "candidate_id", "is_main", "is_active"),
                    to_attr="prefetched_resumes",
                ),
            )
        )

        # Apply search filter by candidate's full name
        if search:
            queryset = queryset.filter(
                Q(candidate__candidateprofile__full_name__icontains=search)
            )

        # Order by the newest message rather than when the conversation was
        # created — otherwise a long-dormant conversation that just received a
        # message stays buried at the bottom of the list, which is exactly
        # where the user will not look for it.
        return queryset.annotate(
            last_activity=Coalesce(Max("messages__created_at"), "created_at")
        ).order_by("-last_activity")


class RecruiterConversationDetailView(generics.RetrieveAPIView):
    """
    Retrieve a specific conversation with all messages.
    
    Only the recruiter who is part of this conversation can access it.
    Viewing this endpoint marks the conversation as read by the recruiter.
    """

    serializer_class = ConversationDetailSerializer
    permission_classes = [IsRecruiterPermission]
    lookup_field = "id"

    def get_queryset(self):
        """
        Return conversation if recruiter is a participant.
        Optimized with select_related and prefetch_related to avoid N+1 queries.
        """
        user = self.request.user

        # Import CompanyProfile for prefetch optimization
        from apps.profiles.models import CompanyProfile

        return (
            Conversation.objects
            .filter(recruiter_id=user.id)
            .select_related(
                "candidate",
                "candidate__candidateprofile",
                "recruiter",
                "recruiter__company",
                "application",
                "application__vacancy",
                "vacancy",  # For headhunting conversations
            )
            .prefetch_related(
                "messages",
                Prefetch(
                    "recruiter__recruiterprofile_set",
                    queryset=RecruiterProfile.objects.only(
                        "id", "recruiter_id", "full_name", "photo"
                    ),
                ),
                Prefetch(
                    "recruiter__company__companyprofile",
                    queryset=CompanyProfile.objects.only(
                        "id", "company_id", "photo"
                    ),
                    to_attr="prefetched_company_profile",
                ),
                Prefetch(
                    "application__documents",
                    queryset=ApplicationDocument.objects.order_by("-created_at"),
                    to_attr="prefetched_documents",
                ),
                Prefetch(
                    "candidate__resumes",
                    queryset=Resume.objects.filter(
                        is_active=True
                    ).only("id", "candidate_id", "is_main", "is_active"),
                    to_attr="prefetched_resumes",
                ),
            )
        )

    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve conversation and mark as read by recruiter.
        Also marks messages from candidate as read.
        """
        instance = self.get_object()

        # Mark as read by recruiter
        if not instance.is_read_by_recruiter:
            instance.is_read_by_recruiter = True
            instance.save(update_fields=["is_read_by_recruiter", "updated_at"])

        # Mark all unread messages from candidate as read
        instance.messages.filter(
            is_read=False,
            sender_type="CANDIDATE"
        ).update(is_read=True)

        # Cache hunting status to avoid N+1 queries in message serialization
        # Check if candidate has applied to the vacancy (for headhunting conversations)
        if instance.vacancy_id:
            from apps.applications.models import JobApplication
            instance._cached_hunting_status = JobApplication.objects.filter(
                candidate_id=instance.candidate_id,
                vacancy_id=instance.vacancy_id
            ).exists()
        else:
            instance._cached_hunting_status = False

        serializer = self.get_serializer(instance)
        return APIResponse.success(data=serializer.data, message=_("Conversation retrieved"))


class CandidateConversationListView(generics.ListAPIView):
    """
    List all conversations for the authenticated candidate.
    
    Shows all conversations with recruiters for vacancies the candidate applied to.
    Supports searching by company name.
    """

    serializer_class = ConversationListSerializer
    permission_classes = [IsCandidatePermission]

    def get_queryset(self):
        """
        Return conversations where the authenticated candidate is a participant.
        Optimized with select_related and prefetch_related to avoid N+1 queries.
        """
        user = self.request.user
        search = self.request.query_params.get('search', '').strip()

        # Import CompanyProfile for prefetch optimization
        from apps.profiles.models import CompanyProfile

        queryset = (
            Conversation.objects
            .filter(candidate_id=user.id)
            .select_related(
                "candidate",
                "candidate__candidateprofile",
                "recruiter",
                "recruiter__company",
                "application",
                "application__vacancy",
                "vacancy",  # For headhunting conversations
            )
            .prefetch_related(
                Prefetch(
                    "messages",
                    queryset=Message.objects.order_by("-created_at")[:1],
                    to_attr="recent_messages",
                ),
                Prefetch(
                    "recruiter__recruiterprofile_set",
                    queryset=RecruiterProfile.objects.only(
                        "id", "recruiter_id", "full_name", "photo"
                    ),
                ),
                Prefetch(
                    "recruiter__company__companyprofile",
                    queryset=CompanyProfile.objects.only(
                        "id", "company_id", "photo"
                    ),
                    to_attr="prefetched_company_profile",
                ),
                Prefetch(
                    "candidate__resumes",
                    queryset=Resume.objects.filter(
                        is_active=True
                    ).only("id", "candidate_id", "is_main", "is_active"),
                    to_attr="prefetched_resumes",
                ),
            )
        )

        # Apply search filter by company name
        if search:
            queryset = queryset.filter(
                Q(recruiter__company__name__icontains=search)
            )

        # Order by the newest message rather than when the conversation was
        # created — otherwise a long-dormant conversation that just received a
        # message stays buried at the bottom of the list, which is exactly
        # where the user will not look for it.
        return queryset.annotate(
            last_activity=Coalesce(Max("messages__created_at"), "created_at")
        ).order_by("-last_activity")


class CandidateConversationDetailView(generics.RetrieveAPIView):
    """
    Retrieve a specific conversation with all messages.
    
    Only the candidate who is part of this conversation can access it.
    Viewing this endpoint marks the conversation as read by the candidate.
    """

    serializer_class = ConversationDetailSerializer
    permission_classes = [IsCandidatePermission]
    lookup_field = "id"

    def get_queryset(self):
        """
        Return conversation if candidate is a participant.
        Optimized with select_related and prefetch_related to avoid N+1 queries.
        """
        user = self.request.user

        # Import CompanyProfile for prefetch optimization
        from apps.profiles.models import CompanyProfile

        return (
            Conversation.objects
            .filter(candidate_id=user.id)
            .select_related(
                "candidate",
                "candidate__candidateprofile",
                "recruiter",
                "recruiter__company",
                "application",
                "application__vacancy",
                "vacancy",  # For headhunting conversations
            )
            .prefetch_related(
                "messages",
                Prefetch(
                    "recruiter__recruiterprofile_set",
                    queryset=RecruiterProfile.objects.only(
                        "id", "recruiter_id", "full_name", "photo"
                    ),
                ),
                Prefetch(
                    "recruiter__company__companyprofile",
                    queryset=CompanyProfile.objects.only(
                        "id", "company_id", "photo"
                    ),
                    to_attr="prefetched_company_profile",
                ),
                Prefetch(
                    "application__documents",
                    queryset=ApplicationDocument.objects.order_by("-created_at"),
                    to_attr="prefetched_documents",
                ),
                Prefetch(
                    "candidate__resumes",
                    queryset=Resume.objects.filter(
                        is_active=True
                    ).only("id", "candidate_id", "is_main", "is_active"),
                    to_attr="prefetched_resumes",
                ),
            )
        )

    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve conversation and mark as read by candidate.
        Also marks messages from recruiter as read.
        """
        instance = self.get_object()

        # Mark as read by candidate
        if not instance.is_read_by_candidate:
            instance.is_read_by_candidate = True
            instance.save(update_fields=["is_read_by_candidate", "updated_at"])

        # Mark all unread messages from recruiter as read
        instance.messages.filter(
            is_read=False,
            sender_type="RECRUITER"
        ).update(is_read=True)

        # Cache hunting status to avoid N+1 queries in message serialization
        # Check if candidate has applied to the vacancy (for headhunting conversations)
        if instance.vacancy_id:
            from apps.applications.models import JobApplication
            instance._cached_hunting_status = JobApplication.objects.filter(
                candidate_id=instance.candidate_id,
                vacancy_id=instance.vacancy_id
            ).exists()
        else:
            instance._cached_hunting_status = False

        serializer = self.get_serializer(instance)
        return APIResponse.success(data=serializer.data, message=_("Conversation retrieved"))


class ConversationUnreadCountView(APIView):
    """
    Number of conversations with unread messages for the current user.

    Drives the badge on the chat icon, so it is polled and pushed at from
    every dashboard page. It stays a single indexed COUNT — no serialization,
    no joins — because it is called far more often than the list itself.

    Works for both candidates and recruiters; the unread flag is per side of
    the conversation, so each user only ever sees their own count.
    """

    permission_classes = [IsCandidateOrRecruiterPermission]

    def get(self, request):
        user = request.user

        if getattr(user, "is_recruiter", False):
            unread = Conversation.objects.filter(
                recruiter_id=user.id, is_read_by_recruiter=False
            ).count()
        else:
            unread = Conversation.objects.filter(
                candidate_id=user.id, is_read_by_candidate=False
            ).count()

        return APIResponse.success(
            data={"unread_conversations": unread},
            message=_("Unread count retrieved"),
        )


recruiter_conversation_list_view = RecruiterConversationListView.as_view()
recruiter_conversation_detail_view = RecruiterConversationDetailView.as_view()
candidate_conversation_list_view = CandidateConversationListView.as_view()
candidate_conversation_detail_view = CandidateConversationDetailView.as_view()
conversation_unread_count_view = ConversationUnreadCountView.as_view()
