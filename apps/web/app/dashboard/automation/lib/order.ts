// The viewer's manual order for the automations list. The backend returns
// every list in it; a drag saves the whole order back (`setAutomationOrder`),
// like the sidebar's project order.
//
// A drag only ever reorders the rows one group shows (a project under "All
// automations", or the one picked project), minus whatever the status filter
// and the search hide. Those rows are dealt back into the slots they held in
// the full list, so rows in other groups and hidden rows keep their place.

import type { AutomationResponse } from '@/lib/backend-api';
import { mergeRenderedOrder } from '@/components/dashboard/session-grouping';

/**
 * The full list after the on-screen rows `rendered` (ids, in their new order)
 * were dragged into place; every other row keeps its slot.
 */
export function reorderRows(
  rows: AutomationResponse[],
  rendered: string[],
): AutomationResponse[] {
  const byId = new Map(rows.map((row) => [row.id, row]));
  return mergeRenderedOrder(
    rows.map((row) => row.id),
    rendered.filter((id) => byId.has(id)),
  ).map((id) => byId.get(id)!);
}
