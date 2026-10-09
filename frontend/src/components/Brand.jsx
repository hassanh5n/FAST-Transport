// Brand marks for dark/gradient surfaces: original-colour mark (background
// removed) with a soft glow so the navy stroke stays visible; white wordmark.

export function BrandMark({ size = 52, style }) {
  return (
    <img
      className="fc-mark"
      src="/fleetcentric-mark.png"
      alt=""
      width="457"
      height="400"
      draggable="false"
      style={{ width: size, height: "auto", ...style }}
    />
  );
}

export function BrandWordmark({ height = 22, style }) {
  return (
    <img
      src="/fleetcentric-wordmark-white.png"
      alt="Fleetcentric.ai"
      width="1065"
      height="127"
      draggable="false"
      style={{ height, width: "auto", display: "block", ...style }}
    />
  );
}

// Mark + wordmark, with an optional caption under the wordmark (auth pages).
export function BrandLockup({ tile = 48, wordHeight = 22, caption }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
      <BrandMark size={tile} />
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <BrandWordmark height={wordHeight} />
        {caption && <h1 className="fc-brand-caption">{caption}</h1>}
      </div>
    </div>
  );
}
