import { expect, test } from '@playwright/test';

const ID = 'scenario-sandbox';

test('incident list links to an incident', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('supply-chain worm. Keep your world');
  await expect(page.getByRole('heading', { name: 'Your containment workspace.' })).toBeVisible();
  await page.getByRole('link', { name: /self-replicating loader/ }).first().click();
  await expect(page).toHaveURL(new RegExp(`/incidents/${ID}`));
});

test('live view shows KPIs and a timeline', async ({ page }) => {
  await page.goto(`/incidents/${ID}/`);
  await expect(page.getByText('Time to containment')).toBeVisible();
  await expect(page.getByText('Secrets exposed')).toBeVisible();
  await expect(page.locator('.event').first()).toBeVisible();
});

test('plan view explains why an action is placed', async ({ page }) => {
  await page.goto(`/incidents/${ID}/plan`);
  await expect(page.getByText('Why the order is safe')).toBeVisible();
  await page.locator('.pnode').first().waitFor();
  await page.locator('.pnode').first().click();
  await expect(page.locator('.explain h3')).toBeVisible();
  await expect(page.locator('.explain')).toContainText(/layer \d/);
});

test('replay shows the sentinel intact for Defuse and destroyed for naive', async ({ page }) => {
  await page.goto(`/incidents/${ID}/replay`);
  await page.getByRole('button', { name: 'Play' }).click();
  await page.waitForTimeout(1600);
  await expect(page.getByText('detonated')).toBeVisible();
  await expect(page.getByText('contained')).toBeVisible();
});

test('record view lists the action ledger', async ({ page }) => {
  await page.goto(`/incidents/${ID}/record`);
  await expect(page.getByText('Action ledger')).toBeVisible();
  await expect(page.locator('tbody tr').first()).toBeVisible();
});

test('named SSE events update the timeline and resume without duplicates', async ({ page }) => {
  let connections = 0;
  let resumed = false;
  await page.route(new RegExp(`/api/incidents/${ID}/events\\?`), async (route) => {
    connections += 1;
    const seq = 100000;
    resumed ||= route.request().url().includes(`last_event_id=${seq}`);
    const event = { seq, kind: 'action', at: new Date().toISOString(),
      payload: { status: 'applied' }, message: 'Browser live event' };
    await route.fulfill({ status: 200, contentType: 'text/event-stream',
      body: `id: ${seq}\nevent: action\ndata: ${JSON.stringify(event)}\n\n` });
  });
  await page.goto(`/incidents/${ID}/`);
  await expect(page.getByText('Browser live event', { exact: true })).toHaveCount(1);
  await expect.poll(() => connections).toBeGreaterThan(1);
  await expect.poll(() => resumed).toBe(true);
  await expect(page.getByText('Browser live event', { exact: true })).toHaveCount(1);
});

for (const view of ['', '/map', '/plan', '/replay', '/record']) {
  test(`mobile layout fits the screen: ${view || 'console'}`, async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(`/incidents/${ID}${view}`);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  });
}


test('landing metrics come from the connected engine', async ({ page, request }) => {
  const incidents = await (await request.get('/api/incidents')).json();
  const metrics = await (await request.get(`/api/incidents/${incidents[0].id}/metrics`)).json();
  const graph = await (await request.get(`/api/incidents/${incidents[0].id}/graph`)).json();
  await page.goto('/');
  await expect(page.locator('.ticket').filter({ hasText: 'Incidents in your workspace' }).locator('strong')).toHaveText(String(incidents.length));
  await expect(page.locator('.ticket').filter({ hasText: 'Actions executed' }).locator('strong')).toHaveText(String(metrics.actions_executed));
  await expect(page.locator('.ticket').filter({ hasText: 'CI jobs exposed' }).locator('strong')).toHaveText(String(graph.nodes.filter((node: { kind: string }) => node.kind === 'job').length));
  await page.getByRole('link', { name: 'Open console', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/incidents/${incidents[0].id}`));
  await expect(page.getByRole('link', { name: 'Live', exact: true })).toHaveAttribute('aria-current', 'page');
});

test('workflow tabs support keyboard navigation and link to the real plan', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('tab', { name: /Map the exposure/ }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: /Plan the safe order/ })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tabpanel')).toContainText('Make the next move safe.');
  await page.getByRole('link', { name: 'Inspect the plan' }).click();
  await expect(page).toHaveURL(new RegExp(`/incidents/${ID}/plan`));
  await expect(page.locator('.pnode').first()).toBeVisible();
});

test('incident search and filters recover from an empty result', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Active', exact: true }).click();
  await expect(page.getByText('No incidents match this view.')).toBeVisible();
  await page.getByRole('button', { name: 'Clear filters' }).click();
  await expect(page.locator('.incident-row')).toHaveCount(1);
  await page.getByRole('searchbox', { name: 'Search incidents' }).fill('no-such-incident');
  await expect(page.getByText('No incidents match this view.')).toBeVisible();
  await page.getByRole('button', { name: 'Clear filters' }).click();
  await expect(page.locator('.incident-row')).toHaveCount(1);
});

test('engine failure is distinct from an empty workspace and can reconnect', async ({ page }) => {
  await page.goto(`/incidents/${ID}/`);
  await page.route('**/api/incidents', route => route.fulfill({ status: 502, body: 'Engine unavailable' }));
  await page.getByRole('link', { name: 'Defuse home', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'The engine is unavailable.' })).toBeVisible();
  await expect(page.locator('.ticket').first().locator('strong')).toHaveText('—');
  await page.unroute('**/api/incidents');
  await page.getByRole('button', { name: 'Reconnect to engine' }).click();
  await expect(page.locator('.incident-row')).toHaveCount(1);
});

test('empty workspace offers a next step without invented metrics', async ({ page }) => {
  await page.goto(`/incidents/${ID}/`);
  await page.route('**/api/incidents', route => route.fulfill({ json: [] }));
  await page.getByRole('link', { name: 'Defuse home', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'A clear workspace.' })).toBeVisible();
  await expect(page.locator('.ticket').first().locator('strong')).toHaveText('0');
  await expect(page.locator('.ticket').nth(1).locator('strong')).toHaveText('—');
});

test('landing fits mobile, theme persists, and reduced motion is respected', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  expect(await page.locator('.cloud-left').evaluate(el => parseFloat(getComputedStyle(el).animationDuration))).toBeLessThan(0.01);
  await page.getByRole('button', { name: 'Switch light or dark theme' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.getByRole('button', { name: 'Switch light or dark theme' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});
