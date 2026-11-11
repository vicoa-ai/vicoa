'use client';

/**
 * A plugin's settings, drawn from the schema in its `plugin.json`.
 *
 * Machine-scope values are read and written through the plugin's daemon (the
 * same on every device); device-scope values stay in this browser. Field
 * kinds follow the declared type: text (or a picker for `enum`), number,
 * switch, a list (one value per line) and JSON for objects.
 */

import { useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getRpcClient } from '@/lib/ws-client';
import { toast } from '@/lib/toast';
import { deviceSettingsStore } from '@/lib/plugins/device-settings';
import { daemonError } from '@/lib/plugins/bridge/host';
import type { PluginSettingSpec, PluginSettingsSchema } from '@/lib/plugins/types';

/** What the user is editing: text for list/object fields until saved. */
type Draft = Record<string, string | number | boolean>;

function toDraft(spec: PluginSettingSpec, value: unknown): string | number | boolean {
  switch (spec.type) {
    case 'boolean':
      return Boolean(value);
    case 'number':
      return typeof value === 'number' ? value : Number(value) || 0;
    case 'array':
      return Array.isArray(value) ? value.join('\n') : '';
    case 'object':
      return JSON.stringify(value ?? {}, null, 2);
    default:
      return typeof value === 'string' ? value : '';
  }
}

/** Turn a field's draft back into its value, or throw a message. */
export function fromDraft(spec: PluginSettingSpec, draft: string | number | boolean): unknown {
  switch (spec.type) {
    case 'boolean':
      return Boolean(draft);
    case 'number': {
      const n = Number(draft);
      if (!Number.isFinite(n)) throw new Error('must be a number');
      return n;
    }
    case 'array':
      return String(draft)
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);
    case 'object': {
      const parsed: unknown = JSON.parse(String(draft) || '{}');
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('must be a JSON object');
      return parsed;
    }
    default:
      return String(draft);
  }
}

export function PluginSettingsForm({ machineId, pluginId }: { machineId: string; pluginId: string }) {
  const [schema, setSchema] = useState<PluginSettingsSchema | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const device = useMemo(() => deviceSettingsStore(pluginId), [pluginId]);

  useEffect(() => {
    let cancelled = false;
    getRpcClient(machineId)
      .callRpc(machineId, 'plugin-settings-get', { plugin_id: pluginId })
      .then((res) => {
        if (cancelled) return;
        const err = daemonError(res);
        if (err) {
          setError(err.code === 'daemon_outdated' ? 'Update Vicoa on this machine to change plugin settings.' : err.message);
          return;
        }
        const s = (res.schema ?? {}) as PluginSettingsSchema;
        const machineValues = (res.values ?? {}) as Record<string, unknown>;
        const deviceValues = device.get();
        const next: Draft = {};
        for (const [key, spec] of Object.entries(s)) {
          const value = spec.scope === 'device' ? (key in deviceValues ? deviceValues[key] : spec.default) : machineValues[key];
          next[key] = toDraft(spec, value ?? spec.default);
        }
        setSchema(s);
        setDraft(next);
      })
      .catch(() => !cancelled && setError("Couldn't reach this machine."));
    return () => {
      cancelled = true;
    };
  }, [machineId, pluginId, device]);

  const save = async () => {
    if (!schema) return;
    const machine: Record<string, unknown> = {};
    const deviceValues: Record<string, unknown> = {};
    for (const [key, spec] of Object.entries(schema)) {
      let value: unknown;
      try {
        value = fromDraft(spec, draft[key]);
      } catch (e) {
        toast.error(`Couldn't save ${spec.title ?? key}`, { description: e instanceof Error ? e.message : undefined });
        return;
      }
      if (spec.scope === 'device') deviceValues[key] = value;
      else machine[key] = value;
    }
    setSaving(true);
    try {
      if (Object.keys(machine).length) {
        const res = await getRpcClient(machineId).callRpc(machineId, 'plugin-settings-set', {
          plugin_id: pluginId,
          values: machine,
        });
        const err = daemonError(res);
        if (err) throw err;
      }
      device.set(deviceValues);
      toast.success('Settings saved');
    } catch (e) {
      toast.error("Couldn't save settings", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setSaving(false);
    }
  };

  if (error) return <p className="text-xs text-muted-foreground">{error}</p>;
  if (!schema) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" /> Loading settings…
      </div>
    );
  }
  const entries = Object.entries(schema);
  if (entries.length === 0) return <p className="text-xs text-muted-foreground">This plugin has no settings.</p>;

  return (
    <div className="space-y-4">
      {entries.map(([key, spec]) => (
        <div key={key} className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-3">
            <label htmlFor={`ps-${pluginId}-${key}`} className="text-[13px] text-foreground">
              {spec.title ?? key}
            </label>
            {spec.scope === 'device' && <span className="text-[11px] text-muted-foreground">This device only</span>}
          </div>
          {spec.description && <p className="text-xs text-muted-foreground">{spec.description}</p>}
          <Field id={`ps-${pluginId}-${key}`} spec={spec} value={draft[key]} onChange={(v) => setDraft((d) => ({ ...d, [key]: v }))} />
        </div>
      ))}
      <div className="flex justify-end">
        <Button size="sm" onClick={() => void save()} disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </div>
  );
}

function Field({
  id,
  spec,
  value,
  onChange,
}: {
  id: string;
  spec: PluginSettingSpec;
  value: string | number | boolean | undefined;
  onChange: (v: string | number | boolean) => void;
}) {
  if (spec.type === 'boolean') {
    return <Switch id={id} checked={Boolean(value)} onCheckedChange={onChange} />;
  }
  if (spec.type === 'string' && spec.enum?.length) {
    return (
      <Select value={String(value ?? '')} onValueChange={onChange}>
        <SelectTrigger id={id} className="h-8 w-full max-w-sm cursor-pointer text-sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {spec.enum.map((option) => (
            <SelectItem key={option} value={option} className="cursor-pointer text-sm">
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }
  if (spec.type === 'array' || spec.type === 'object') {
    return (
      <textarea
        id={id}
        value={String(value ?? '')}
        onChange={(e) => onChange(e.target.value)}
        rows={spec.type === 'object' ? 6 : 4}
        spellCheck={false}
        placeholder={spec.type === 'array' ? 'One per line' : '{}'}
        className="custom-scrollbar w-full max-w-xl rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs outline-none focus-visible:ring-1 focus-visible:ring-ring"
      />
    );
  }
  return (
    <Input
      id={id}
      type={spec.type === 'number' ? 'number' : 'text'}
      value={String(value ?? '')}
      onChange={(e) => onChange(spec.type === 'number' ? e.target.value : e.target.value)}
      className="h-8 max-w-sm text-sm"
    />
  );
}
