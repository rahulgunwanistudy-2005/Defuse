import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
  const [graph, metrics, events] = await Promise.all([
    api.graph(fetch, params.id).catch(() => null),
    api.metrics(fetch, params.id).catch(() => null),
    api.events(fetch, params.id).catch(() => [])
  ]);
  return { id: params.id, graph, metrics, events };
};
