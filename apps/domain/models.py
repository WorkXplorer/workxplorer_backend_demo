from django.db import models
from django.utils.translation import gettext_lazy as _
from utils import AbstractBaseModel


class Domain(AbstractBaseModel):
    """
    Domain model to categorize professions and vacancies.
    Will be used for filtering vacancies and connecting with Profession in quizapp.
    """

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name=_("Name"),
        help_text=_("Domain name (e.g., IT, Healthcare, Finance)"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Detailed description of the domain"),
    )
    category = models.ForeignKey(
        "skills.SkillCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="domains",
        verbose_name=_("Skill Category"),
        help_text=_("The skill category that best represents this domain's primary skills"),
    )
    sector_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Sector Code"),
        help_text=_(
            "Official statistics sector this domain maps to (e.g. stat.uz sector "
            "classification), used to cross-reference market salary estimates "
            "against government wage data. Assigned once per domain, not per request."
        ),
    )

    class Meta:
        verbose_name = _("Domain")
        verbose_name_plural = _("Domains")
        ordering = ["name"]

    def __str__(self) -> str:
        return str(self.name)


class HrCreatedProfession(AbstractBaseModel):
    """
    Profession model created by HR within a company.
    """

    company = models.ForeignKey(
        "authentication.Company",
        on_delete=models.CASCADE,
        related_name="hr_created_professions",
        verbose_name=_("Company"),
        help_text=_("The company that created this profession"),
    )
    name = models.CharField(
        max_length=255,
        verbose_name=_("Profession Name"),
        help_text=_("Name of the profession created by HR"),
    )
    description = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Description of the profession"),
    )
    created_by = models.ForeignKey(
        "authentication.Recruiter",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_professions",
        verbose_name=_("Created By"),
        help_text=_("The recruiter who created this profession"),
    )

    def __str__(self) -> str:
        return str(self.name)

    class Meta:
        verbose_name = _("HR Created Profession")
        verbose_name_plural = _("HR Created Professions")
        ordering = ["name"]
