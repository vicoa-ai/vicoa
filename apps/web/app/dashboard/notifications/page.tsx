'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Bell, BellOff, Smartphone, TestTube, Loader2 } from 'lucide-react';
import { PushNotificationService } from '@/lib/push-notifications';

interface NotificationSettings {
  push_enabled: boolean;
  email_enabled: boolean;
  agent_status_changes: boolean;
  agent_messages: boolean;
  system_updates: boolean;
}

export default function NotificationsPage() {
  const [isSupported, setIsSupported] = useState(false);
  const [permission, setPermission] = useState<NotificationPermission>('default');
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [settings, setSettings] = useState<NotificationSettings>({
    push_enabled: false,
    email_enabled: true,
    agent_status_changes: true,
    agent_messages: true,
    system_updates: false,
  });

  const pushService = PushNotificationService.getInstance();

  useEffect(() => {
    initializeNotifications();
    loadSettings();
  }, []);

  const initializeNotifications = async () => {
    const supported = await pushService.initialize();
    setIsSupported(supported);
    
    if (supported) {
      setPermission(Notification.permission);
      
      // Check if already subscribed
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      setIsSubscribed(!!subscription);
    }
    
    setIsLoading(false);
  };

  const loadSettings = async () => {
    try {
      const response = await fetch('/api/agent-dashboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint: '/api/v1/user/notification-settings',
          method: 'GET'
        })
      });

      if (response.ok) {
        const serverSettings = await response.json();
        setSettings({ ...settings, ...serverSettings });
      }
    } catch (error) {
      console.error('Failed to load notification settings:', error);
    }
  };

  const saveSettings = async (newSettings: NotificationSettings) => {
    try {
      const response = await fetch('/api/agent-dashboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint: '/api/v1/user/notification-settings',
          method: 'PUT',
          data: newSettings
        })
      });

      if (response.ok) {
        setSettings(newSettings);
        console.log('Settings saved successfully');
      } else {
        throw new Error('Failed to save settings');
      }
    } catch (error) {
      console.error('Failed to save notification settings:', error);
      alert('Failed to save settings');
    }
  };

  const handleEnablePushNotifications = async () => {
    try {
      setIsLoading(true);

      // Request permission
      const permission = await pushService.requestPermission();
      setPermission(permission);

      if (permission !== 'granted') {
        alert('Push notifications permission denied');
        return;
      }

      // Subscribe to push notifications
      const subscription = await pushService.subscribe();
      if (!subscription) {
        alert('Failed to subscribe to push notifications');
        return;
      }

      // Register with server
      const registered = await pushService.registerWithServer(subscription);
      if (!registered) {
        alert('Failed to register push notifications with server');
        return;
      }

      setIsSubscribed(true);
      
      // Update settings
      const newSettings = { ...settings, push_enabled: true };
      await saveSettings(newSettings);

      alert('Push notifications enabled successfully!');
    } catch (error) {
      console.error('Failed to enable push notifications:', error);
      alert('Failed to enable push notifications');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDisablePushNotifications = async () => {
    try {
      setIsLoading(true);

      // Unsubscribe
      const unsubscribed = await pushService.unsubscribe();
      if (!unsubscribed) {
        alert('Failed to unsubscribe from push notifications');
        return;
      }

      setIsSubscribed(false);
      
      // Update settings
      const newSettings = { ...settings, push_enabled: false };
      await saveSettings(newSettings);

      alert('Push notifications disabled successfully!');
    } catch (error) {
      console.error('Failed to disable push notifications:', error);
      alert('Failed to disable push notifications');
    } finally {
      setIsLoading(false);
    }
  };

  const handleTestNotification = async () => {
    try {
      await pushService.testNotification();
      alert('Test notification sent! Check your notifications.');
    } catch (error) {
      console.error('Failed to send test notification:', error);
      alert('Failed to send test notification');
    }
  };

  const handleSettingChange = (key: keyof NotificationSettings, value: boolean) => {
    const newSettings = { ...settings, [key]: value };
    saveSettings(newSettings);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="text-lg">Loading notification settings...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl">Notification Settings</h1>
          <p className="text-muted-foreground">Manage how you receive notifications from your agents</p>
        </div>

        {/* Push Notifications */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Smartphone className="w-5 h-5" />
              Push Notifications
            </CardTitle>
            <CardDescription>
              Receive real-time notifications in your browser
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!isSupported ? (
              <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-yellow-800">
                  Push notifications are not supported in this browser.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium">Browser Notifications</div>
                    <div className="text-sm text-muted-foreground">
                      Status: {permission === 'granted' ? 'Allowed' : 
                              permission === 'denied' ? 'Blocked' : 'Not requested'}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    {!isSubscribed ? (
                      <Button
                        onClick={handleEnablePushNotifications}
                        disabled={isLoading}
                      >
                        <Bell className="w-4 h-4 mr-2" />
                        Enable Push Notifications
                      </Button>
                    ) : (
                      <>
                        <Button
                          variant="outline"
                          onClick={handleTestNotification}
                          disabled={isLoading}
                        >
                          <TestTube className="w-4 h-4 mr-2" />
                          Test
                        </Button>
                        <Button
                          variant="outline"
                          onClick={handleDisablePushNotifications}
                          disabled={isLoading}
                        >
                          <BellOff className="w-4 h-4 mr-2" />
                          Disable
                        </Button>
                      </>
                    )}
                  </div>
                </div>

                {permission === 'denied' && (
                  <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                    <p className="text-red-800">
                      Push notifications are blocked. Please enable them in your browser settings.
                    </p>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Notification Preferences */}
        <Card>
          <CardHeader>
            <CardTitle>Notification Preferences</CardTitle>
            <CardDescription>
              Choose what types of notifications you want to receive
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Agent Status Changes</div>
                  <div className="text-sm text-muted-foreground">
                    When agents start, stop, or change status
                  </div>
                </div>
                <Button
                  variant={settings.agent_status_changes ? "default" : "outline"}
                  size="sm"
                  onClick={() => handleSettingChange('agent_status_changes', !settings.agent_status_changes)}
                >
                  {settings.agent_status_changes ? 'On' : 'Off'}
                </Button>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Agent Messages</div>
                  <div className="text-sm text-muted-foreground">
                    When agents need input or send messages
                  </div>
                </div>
                <Button
                  variant={settings.agent_messages ? "default" : "outline"}
                  size="sm"
                  onClick={() => handleSettingChange('agent_messages', !settings.agent_messages)}
                >
                  {settings.agent_messages ? 'On' : 'Off'}
                </Button>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">System Updates</div>
                  <div className="text-sm text-muted-foreground">
                    Important system announcements and updates
                  </div>
                </div>
                <Button
                  variant={settings.system_updates ? "default" : "outline"}
                  size="sm"
                  onClick={() => handleSettingChange('system_updates', !settings.system_updates)}
                >
                  {settings.system_updates ? 'On' : 'Off'}
                </Button>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Email Notifications</div>
                  <div className="text-sm text-muted-foreground">
                    Receive notifications via email
                  </div>
                </div>
                <Button
                  variant={settings.email_enabled ? "default" : "outline"}
                  size="sm"
                  onClick={() => handleSettingChange('email_enabled', !settings.email_enabled)}
                >
                  {settings.email_enabled ? 'On' : 'Off'}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}