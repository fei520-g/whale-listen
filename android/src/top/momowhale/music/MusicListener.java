package top.momowhale.music;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
public final class MusicListener extends NotificationListenerService {
 @Override public void onListenerConnected(){SyncService.refreshIfRunning();}
 @Override public void onListenerDisconnected(){SyncService.permissionLost();}
 @Override public void onNotificationPosted(StatusBarNotification item){if(MediaTracker.isKugou(item.getPackageName()))SyncService.refreshIfRunning();}
 @Override public void onNotificationRemoved(StatusBarNotification item){if(MediaTracker.isKugou(item.getPackageName()))SyncService.refreshIfRunning();}
 // Notification contents are deliberately never accessed, stored, or uploaded.
}
