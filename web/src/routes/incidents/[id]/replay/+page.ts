import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
  const [replay, plan, naive] = await Promise.all([
    api.replay(fetch, params.id),
    api.plan(fetch, params.id, 'defuse'),
    api.plan(fetch, params.id, 'naive')
  ]);
  return { id: params.id, replay, plan, naive };
};
