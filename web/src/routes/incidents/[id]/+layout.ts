import { api } from '$lib/api';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ fetch, params }) => {
  const incident = await api.incident(fetch, params.id);
  return { incident };
};
