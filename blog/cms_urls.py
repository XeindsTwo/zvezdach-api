from django.urls import path

from . import cms_views

app_name = "cms"

urlpatterns = [
    path("login/", cms_views.CmsLoginView.as_view(), name="login"),
    path("logout/", cms_views.cms_logout, name="logout"),
    path("", cms_views.dashboard, name="dashboard"),
    path("articles/", cms_views.article_list, name="article-list"),
    path("articles/new/", cms_views.article_form, name="article-create"),
    path("articles/<int:pk>/", cms_views.article_form, name="article-edit"),
    path("articles/<int:pk>/delete/", cms_views.article_delete, name="article-delete"),
    path("categories/", cms_views.category_list, name="category-list"),
    path("categories/new/", cms_views.category_form, name="category-create"),
    path("categories/<int:pk>/", cms_views.category_form, name="category-edit"),
    path("tags/", cms_views.tag_list, name="tag-list"),
    path("tags/search/", cms_views.tag_search, name="tag-search"),
    path("uploads/images/", cms_views.image_upload, name="image-upload"),
]
