from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("send-message/", views.send_message, name="send_message"),
    path("new-chat/", views.new_chat, name="new_chat"),
    path("switch-chat/<str:chat_id>/", views.switch_chat, name="switch_chat"),
    path("delete-chat/<str:chat_id>/", views.delete_chat, name="delete_chat"),
    path("clear-history/", views.clear_history, name="clear_history"),
]