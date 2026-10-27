<script lang="ts">
  let { glass = false }: { glass?: boolean } = $props();
  const tiles = [
    [1, 13, 64], [6, 3, 64], [11, 13, 64], [6, 24, 64], [16, 3, 64], [21, 13, 64],
    [84, 4, 64], [89, 14, 64], [94, 4, 64], [79, 14, 64], [84, 25, 64], [99, 15, 64],
    [1, 70, 76], [7, 79, 76], [13, 70, 76], [7, 89, 76],
    [87, 69, 76], [93, 79, 76], [99, 69, 76], [87, 89, 76]
  ];
</script>

<div class="tiles" class:glass aria-hidden="true">
  {#each tiles as [x, y, size], i (i)}
    <span style={`--x:${x}%;--y:${y}%;--size:${size}px;--delay:${i % 5 * -1.7}s`}></span>
  {/each}
</div>

<style>
  .tiles { position: absolute; inset: 0; overflow: hidden; pointer-events: none; }
  span { position: absolute; left: var(--x); top: var(--y); width: var(--size); aspect-ratio: 1; border: 1px solid var(--line); border-radius: 12px; opacity: .6; }
  .glass span { border-color: #fff9; background: #ffffff10; backdrop-filter: blur(7px); box-shadow: inset 0 0 10px #ffffff15; animation: drift 9s ease-in-out infinite alternate; animation-delay: var(--delay); }
  .glass span:nth-child(-n+12) { opacity: .28; }
  @keyframes drift { from { transform: translateY(0); } to { transform: translateY(-12px); } }
  @media (max-width: 700px) { span { width: 42px; border-radius: 9px; } .tiles span:nth-child(3n) { display: none; } }
</style>
