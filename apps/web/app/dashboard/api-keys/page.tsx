'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Eye, EyeOff, Copy, Check, Trash2, Plus, Loader2 } from 'lucide-react';
import { getBackendAPI, APIKeyResponse } from '@/lib/backend-api';
import { Terminal } from '@/components/terminal';

export default function ApiKeysPage() {
  // Add CSS to hide scrollbar
  const scrollbarHiddenStyle = `
    .scrollbar-hidden::-webkit-scrollbar {
      display: none;
    }
    .scrollbar-hidden {
      -ms-overflow-style: none;
      scrollbar-width: none;
    }
  `;
  const [apiKeys, setApiKeys] = useState<APIKeyResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [visibleKeys, setVisibleKeys] = useState<Set<string>>(new Set());
  const [copiedKeys, setCopiedKeys] = useState<Set<string>>(new Set());
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [creatingKey, setCreatingKey] = useState(false);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  const [newApiKey, setNewApiKey] = useState<string | null>(null);

  const backendAPI = getBackendAPI();

  useEffect(() => {
    loadApiKeys();
  }, []);

  const loadApiKeys = async () => {
    try {
      setLoading(true);
      setError(null);
      const allKeys = await backendAPI.listApiKeys();
      const activeKeys = allKeys.filter(key => key.is_active);
      setApiKeys(activeKeys);
    } catch (err) {
      setError('Failed to load API keys');
    } finally {
      setLoading(false);
    }
  };

  const toggleKeyVisibility = (keyId: string) => {
    const newVisibleKeys = new Set(visibleKeys);
    if (newVisibleKeys.has(keyId)) {
      newVisibleKeys.delete(keyId);
    } else {
      newVisibleKeys.add(keyId);
    }
    setVisibleKeys(newVisibleKeys);
  };

  const copyToClipboard = async (keyId: string, apiKey: string) => {
    try {
      await navigator.clipboard.writeText(apiKey);
      const newCopiedKeys = new Set(copiedKeys);
      newCopiedKeys.add(keyId);
      setCopiedKeys(newCopiedKeys);
      
      setTimeout(() => {
        const updatedCopiedKeys = new Set(copiedKeys);
        updatedCopiedKeys.delete(keyId);
        setCopiedKeys(updatedCopiedKeys);
      }, 2000);
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
    }
  };

  const deleteApiKey = async (keyId: string) => {
    if (!confirm('Are you sure you want to delete this API key?')) {
      return;
    }

    try {
      setError(null);
      setDeletingKey(keyId);
      
      await backendAPI.revokeApiKey(keyId);
      await loadApiKeys();
    } catch (err) {
      setError('Failed to delete API key');
    } finally {
      setDeletingKey(null);
    }
  };

  const createApiKey = async () => {
    if (!newKeyName.trim()) {
      setError('Please enter a name for the API key');
      return;
    }

    try {
      setCreatingKey(true);
      setError(null);
      
      const result = await backendAPI.createApiKey({ 
        name: newKeyName.trim() 
      });
      
      setNewApiKey(result.api_key);
      setNewKeyName('');
      await loadApiKeys();
    } catch (err) {
      setError('Failed to create API key');
    } finally {
      setCreatingKey(false);
    }
  };

  const handleCreateFormClose = () => {
    setShowCreateForm(false);
    setNewApiKey(null);
    setNewKeyName('');
    if (error) setError(null);
  };

  const maskApiKey = (apiKey: string) => {
    if (apiKey.length <= 8) return '*'.repeat(apiKey.length);
    return apiKey.slice(0, 4) + '*'.repeat(apiKey.length - 8) + apiKey.slice(-4);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading) {
      return (
       <div className="container max-w-4xl mx-auto p-6 font-mono">
         <div className="flex items-center justify-center h-64">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span className="text-lg">Loading API keys...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: scrollbarHiddenStyle }} />
      <div className="container max-w-4xl mx-auto p-6 font-mono">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl">API Keys</h1>
          <p className="text-muted-foreground">Manage your API keys for accessing the Vicoa API</p>
        </div>
        <Button onClick={() => setShowCreateForm(!showCreateForm)}>
          <Plus className="mr-2 h-4 w-4" />
          Create API Key
        </Button>
      </div>

      {showCreateForm && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-lg">Create New API Key</CardTitle>
            <CardDescription>
              Generate a new API key for accessing the Vicoa API
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!newApiKey ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="keyName">Key Name</Label>
                  <Input
                    id="keyName"
                    placeholder="e.g., Development, Production, CLI"
                    value={newKeyName}
                    onChange={(e) => setNewKeyName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !creatingKey) {
                        createApiKey();
                      }
                    }}
                  />
                </div>
                
                <div className="flex gap-2">
                  <Button onClick={createApiKey} disabled={creatingKey} className="flex-1">
                    {creatingKey ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                        Creating...
                      </>
                    ) : (
                      'Create API Key'
                    )}
                  </Button>
                  <Button variant="outline" onClick={handleCreateFormClose}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
                  <div className="flex items-center space-x-2">
                    <Check className="h-4 w-4 text-green-600" />
                    <p className="text-sm font-medium text-green-800 dark:text-green-200">API Key Created Successfully</p>
                  </div>
                </div>
                
                <Button onClick={handleCreateFormClose} className="w-full">
                  Done
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {error && (
        <Card className="mb-6 border-destructive">
          <CardContent>
            <p className="text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {apiKeys.length === 0 ? (
        <Card>
          <CardContent>
            <div className="text-center py-8">
              <div className="text-lg font-medium mb-2">No API keys found</div>
              <p className="text-muted-foreground mb-4">Create your first API key to get started</p>
{/*               
              <Button onClick={() => setShowCreateForm(!showCreateForm)}>
                <Plus className="mr-2 h-4 w-4" />
                Create API Key
              </Button>
              <div className="flex items-center justify-center my-6">
                <div className="flex-1 border-t border-border"></div>
                <span className="mx-4 text-sm text-muted-foreground font-medium">OR</span>
                <div className="flex-1 border-t border-border"></div>
              </div>
              
              <p className="text-muted-foreground mb-4">Run the command in your terminal to get started</p>
              <Terminal /> */}
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {apiKeys.map((key) => (
            <Card key={key.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-lg">{key.name}</CardTitle>
                    <CardDescription>
                      Created {formatDate(key.created_at)}
                      {key.expires_at && ` • Expires ${formatDate(key.expires_at)}`}
                    </CardDescription>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => deleteApiKey(key.id)}
                    disabled={deletingKey === key.id}
                    className="text-red-700 hover:text-red-600 disabled:opacity-50"
                  >
                    {deletingKey === key.id ? (
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-current"></div>
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  <div className={`flex-1 font-mono text-sm bg-muted p-3 rounded-md ${visibleKeys.has(key.id) ? 'overflow-x-auto scrollbar-hidden' : 'overflow-hidden'}`}>
                    <div className={visibleKeys.has(key.id) ? 'whitespace-nowrap' : 'truncate'}>
                      {visibleKeys.has(key.id) ? key.api_key : maskApiKey(key.api_key)}
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => toggleKeyVisibility(key.id)}
                  >
                    {visibleKeys.has(key.id) ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => copyToClipboard(key.id, key.api_key)}
                  >
                    {copiedKeys.has(key.id) ? (
                      <Check className="h-4 w-4 text-green-600" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      </div>
    </>
  );
}