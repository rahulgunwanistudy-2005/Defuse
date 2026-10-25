import { api } from '$lib/api';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
  const incidents = await api.incidents(fetch);
  return { incidents };
};
