import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
  let incidents;
  try {
    incidents = await api.incidents(fetch);
  } catch {
    return { incidents: [], featured: null, graph: null, metrics: null, unavailable: true };
  }
  const featured = incidents[0] ?? null;
  const [graph, metrics] = featured ? await Promise.all([
    api.graph(fetch, featured.id).catch(() => null),
    api.metrics(fetch, featured.id).catch(() => null)
  ]) : [null, null];
  return { incidents, featured, graph, metrics, unavailable: false };
};
