from rest_framework import serializers
from apps.applications.models import JobApplication


class HiredCandidateSerializer(serializers.ModelSerializer):
    """
    Serializer for hired candidates (applications with OFFER_ACCEPTED status).
    
    Provides a simplified view of hired candidates with essential information:
    - Candidate details (name, phone, photo)
    - Vacancy information (title, id)
    - Hiring timestamp
    - Resume ID (resume_used -> main resume -> first resume -> null)
    """

    candidate_id = serializers.UUIDField(source='candidate.id', read_only=True)
    candidate_email = serializers.EmailField(source='candidate.email', read_only=True)
    full_name = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    title = serializers.CharField(source='vacancy.title', read_only=True)
    vacancy_id = serializers.UUIDField(source='vacancy.id', read_only=True)
    resume_id = serializers.SerializerMethodField()

    class Meta:
        model = JobApplication
        fields = [
            'id',
            'candidate_id',
            'candidate_email',
            'full_name',
            'title',
            'hired_at',
            'phone_number',
            'photo',
            'vacancy_id',
            'resume_id',
        ]
        read_only_fields = fields

    def get_full_name(self, obj):
        """
        Get candidate's full name from profile, fallback to email.
        """
        try:
            return obj.candidate.candidateprofile.full_name
        except Exception:
            return obj.candidate.email

    def get_phone_number(self, obj):
        """
        Get candidate's phone number from profile.
        """
        try:
            return obj.candidate.candidateprofile.phone
        except Exception:
            return None

    def get_photo(self, obj):
        """
        Get candidate's photo URL from profile with full URL.
        """
        try:
            profile = obj.candidate.candidateprofile
            if profile.photo:
                request = self.context.get("request")
                if request:
                    return request.build_absolute_uri(profile.photo.url)
                return profile.photo.url
            return None
        except Exception:
            return None

    def get_resume_id(self, obj):
        """
        Get resume ID with the following priority:
        1. resume_used from the application
        2. candidate's main resume (is_main=True)
        3. first active resume of the candidate
        4. null if none found
        
        Uses prefetched resumes to avoid additional queries.
        """
        # 1. Check resume_used from application
        if obj.resume_used_id:
            return obj.resume_used_id

        # 2 & 3. Use prefetched resumes if available
        candidate_resumes = getattr(obj.candidate, 'prefetched_resumes', None)

        if candidate_resumes is not None:
            # Already prefetched - find main or first resume
            for resume in candidate_resumes:
                if resume.is_main:
                    return resume.id
            # No main resume, return first one
            if candidate_resumes:
                return candidate_resumes[0].id
        else:
            # Fallback to database query if not prefetched
            # This should not happen if view is properly optimized
            from apps.resumes.models import Resume
            resume = (
                Resume.objects
                .filter(candidate=obj.candidate, is_active=True)
                .order_by('-is_main', '-created_at')
                .values_list('id', flat=True)
                .first()
            )
            return resume

        return None
