import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
  const graph = await api.graph(fetch, params.id);
  return { id: params.id, graph };
};
