// Service Worker for Push Notifications
self.addEventListener('push', function(event) {
  console.log('[Service Worker] Push received.');
  
  if (event.data) {
    const data = event.data.json();
    console.log('[Service Worker] Push data: ', data);
    
    const title = data.title || 'Agent Dashboard';
    const options = {
      body: data.body || 'You have a new notification',
      icon: '/favicon.ico',
      badge: '/favicon.ico',
      data: data.data || {},
      requireInteraction: true,
      actions: data.actions || []
    };
    
    event.waitUntil(
      self.registration.showNotification(title, options)
    );
  }
});

self.addEventListener('notificationclick', function(event) {
  console.log('[Service Worker] Notification click received.');
  
  event.notification.close();
  
  const url = event.notification.data.url || '/dashboard/agents';
  
  event.waitUntil(
    clients.openWindow(url)
  );
});

self.addEventListener('install', function(event) {
  console.log('[Service Worker] Installing...');
  self.skipWaiting();
});

self.addEventListener('activate', function(event) {
  console.log('[Service Worker] Activating...');
  event.waitUntil(self.clients.claim());
});