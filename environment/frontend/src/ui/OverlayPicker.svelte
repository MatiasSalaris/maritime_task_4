<script>
  import { mapOverlay } from '../store/worldStore.js'
  import { OVERLAYS } from '../map/overlays/index.js'

  export let onSwitch = () => {}

  function pick(id) {
    mapOverlay.set(id)
    onSwitch(id)
  }
</script>

<div class="picker">
  {#each OVERLAYS as o}
    <button
      class="btn"
      class:active={$mapOverlay === o.id}
      on:click={() => pick(o.id)}
    >{o.label}</button>
  {/each}
</div>

<style>
  .picker {
    display: flex;
    gap: 5px;
    background: rgba(6,12,24,0.88);
    border: 1px solid #1a2a3a;
    border-radius: 7px;
    padding: 5px;
    backdrop-filter: blur(8px);
  }
  .btn {
    background: transparent;
    border: 1px solid #1a3a4a;
    color: #8ab0c0;
    font-family: monospace;
    font-size: 12px;
    padding: 5px 12px;
    border-radius: 5px;
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    transition: all 0.15s;
  }
  .btn:hover  { background: #0d2030; color: #c8d8e8; }
  .btn.active { background: #0d2a3a; border-color: #00d4ff; color: #00d4ff; }
</style>
