import { expect, test } from '@playwright/test';

const ID = 'scenario-sandbox';

test('incident list links to an incident', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('supply-chain worm');
  await expect(page.getByText('23%')).toBeVisible();
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
