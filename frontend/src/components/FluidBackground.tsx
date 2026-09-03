/** 全局流体极光背景：多层渐变 blob 缓慢漂移 + 形变，营造流动氛围 */
export default function FluidBackground({ dark = false }: { dark?: boolean }) {
  return (
    <div className={`fluid-field ${dark ? "fluid-dark" : ""}`} aria-hidden>
      <div className="fluid-blob fluid-blob-1" />
      <div className="fluid-blob fluid-blob-2" />
      <div className="fluid-blob fluid-blob-3" />
      <div className="fluid-blob fluid-blob-4" />
      <div className="fluid-grid" />
    </div>
  );
}
