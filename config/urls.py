from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import include, path

from accounts import views as account_views
from datasets import report_views as dataset_report_views


admin.site.site_header = "Administration de la plateforme HCP"
admin.site.site_title = "Administration HCP"
admin.site.index_title = "Pilotage et administration"
admin.site.enable_nav_sidebar = False
admin.site.empty_value_display = "—"


urlpatterns = [
    path(
        "",
        account_views.home,
        name="home",
    ),

    path(
        "admin/",
        admin.site.urls,
    ),

    path(
        "accounts/logout/",
        LogoutView.as_view(
            template_name="registration/logged_out.html",
        ),
        name="logout",
    ),

    path(
        "accounts/",
        include("django.contrib.auth.urls"),
    ),

    path(
        "datasets/",
        include("datasets.urls"),
    ),

    # Une seule source de vérité pour les tableaux de bord.
    # Les routes créer/modifier se trouvent dans dashboards.urls.
    path(
        "dashboards/",
        include("dashboards.urls"),
    ),

    path(
        "assistant/jeu-donnees/<int:pk>/rapport/",
        dataset_report_views.rapport_statistique,
        name="ancien_rapport_statistique",
    ),

    path(
        "assistant/",
        include("ai_assistant.urls"),
    ),

    path(
        "audit/",
        include("audit.urls"),
    ),

    path(
        "",
        include("accounts.urls"),
    ),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
