import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
  const [actions, metrics] = await Promise.all([
    api.actions(fetch, params.id),
    api.metrics(fetch, params.id).catch(() => null)
  ]);
  return { id: params.id, actions, metrics };
};
