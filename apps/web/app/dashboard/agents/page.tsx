'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Plus, Loader2 } from 'lucide-react';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { useDashboardNavigation } from '@/lib/contexts/dashboard-navigation-context';
import { getAgentStatusColors } from '@/lib/agent-status-colors';
import { UserAgentResponse } from '@/lib/backend-api';

function AgentStatusBadge({ status }: { status: string }) {
  const config = getAgentStatusColors(status);

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${config.text} ${config.badgeBg}`}>
      <div className={`w-2 h-2 rounded-full ${config.dot} mr-1.5`} />
      {status}
    </span>
  );
}

function CreateAgentDialog({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [name, setName] = useState('');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      const response = await fetch('/api/agent-dashboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint: '/api/v1/user-agents',
          method: 'POST',
          data: {
            name,
            webhook_url: webhookUrl || null,
            is_active: true,
          },
        }),
      });

      if (response.ok) {
        onSuccess();
        onClose();
      } else {
        throw new Error('Failed to create agent');
      }
    } catch (error) {
      console.error('Failed to create agent:', error);
      alert('Failed to create agent');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background border p-6 rounded-lg max-w-md w-full mx-4">
        <h3 className="text-lg mb-4">Create New Agent</h3>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="name">Agent Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Agent"
              required
            />
          </div>
          <div>
            <Label htmlFor="webhook">Webhook URL (Optional)</Label>
            <Input
              id="webhook"
              type="url"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://example.com/webhook"
            />
          </div>
          <div className="flex gap-2 justify-end">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? 'Creating...' : 'Create Agent'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function AgentsContent() {
  const { api, recentInstances, isLoading, error, refreshData } = useAgentDashboard();
  const { openSession } = useDashboardNavigation();
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [userAgents, setUserAgents] = useState<UserAgentResponse[]>([]);

  useEffect(() => {
    if (api) {
      api.listUserAgents().then(setUserAgents).catch(() => {});
    }
  }, [api]);

  const handleCreateSuccess = () => {
    refreshData();
    if (api) {
      api.listUserAgents().then(setUserAgents).catch(() => {});
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="text-lg">Loading agents...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-red-600">Error: {error}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl">Agent Dashboard</h1>
          <p className="text-muted-foreground">Manage your AI agents and monitor their activity</p>
        </div>
        {/* <Button onClick={() => setShowCreateDialog(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Create Agent
        </Button> */}
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Agents</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold">{userAgents.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Active Sessions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold">
              {userAgents.reduce((sum, agent) => sum + agent.active_instance_count, 0)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Waiting Sessions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold">
              {userAgents.reduce((sum, agent) => sum + agent.waiting_instance_count, 0)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Completed</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold">
              {userAgents.reduce((sum, agent) => sum + agent.completed_instance_count, 0)}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* User Agents */}
      <Card>
        <CardHeader>
          <CardTitle>Your Agents</CardTitle>
          <CardDescription>Manage your configured AI agents</CardDescription>
        </CardHeader>
        <CardContent>
          {userAgents.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-muted-foreground mb-4">No agents configured yet</p>
              <Button onClick={() => setShowCreateDialog(true)}>
                <Plus className="w-4 h-4 mr-2" />
                Create Your First Agent
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {userAgents.map((agent) => (
                <div key={agent.id} className="border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="">{agent.name}</h3>
                    <div className="flex items-center gap-2">
                      {agent.has_webhook && (
                        <span className="text-xs bg-blue-100 dark:bg-blue-900/20 text-blue-800 dark:text-blue-400 px-2 py-1 rounded">
                          Webhook
                        </span>
                      )}
                      <span className={`text-xs px-2 py-1 rounded ${agent.is_active ? 'bg-green-100 dark:bg-green-900/20 text-green-800 dark:text-green-400' : 'bg-muted text-muted-foreground'}`}>
                        {agent.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm text-muted-foreground">
                    <div>
                      <span className="font-medium">Total: </span>
                      {agent.instance_count}
                    </div>
                    <div>
                      <span className="font-medium">Active: </span>
                      {agent.active_instance_count}
                    </div>
                    <div>
                      <span className="font-medium">Waiting: </span>
                      {agent.waiting_instance_count}
                    </div>
                    <div>
                      <span className="font-medium">Completed: </span>
                      {agent.completed_instance_count}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent Instances */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
          <CardDescription>Latest agent instances across all types</CardDescription>
        </CardHeader>
        <CardContent>
          {recentInstances.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">No recent activity</p>
          ) : (
            <div className="space-y-3">
              {recentInstances.map((instance) => (
                <div key={instance.id} className="flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50">
                  <div className="flex-1">
                    <div className="font-medium">{instance.name || instance.agent_type_name || 'Unnamed Instance'}</div>
                    {instance.latest_message && (
                      <div className="text-sm text-foreground/80 mb-1 truncate max-w-md">
                        {instance.latest_message}
                      </div>
                    )}
                    <div className="text-sm text-muted-foreground">
                      {new Date(instance.started_at).toLocaleString()}
                    </div>
                  </div>
                  <div className="text-right flex items-center gap-3">
                    <div>
                      <AgentStatusBadge status={instance.status} />
                      {/* {instance.chat_length > 0 && (
                        <div className="text-sm text-muted-foreground mt-1">
                          {instance.chat_length} messages
                        </div>
                      )} */}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => openSession(instance.id)}
                    >
                      View
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {showCreateDialog && (
        <CreateAgentDialog 
          onClose={() => setShowCreateDialog(false)}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  );
}

export default function AgentsPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 font-mono">
      <AgentsContent />
    </div>
  );
}
