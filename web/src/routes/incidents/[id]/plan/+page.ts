import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
  const plan = await api.plan(fetch, params.id, 'defuse');
  return { id: params.id, plan };
};
