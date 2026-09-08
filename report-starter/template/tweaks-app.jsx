// Tweaks app — switches the report's theme / accent / motif.
// Applies tweak values to the live document (vanilla report reads CSS vars + data-theme).
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "mosaic",
  "accent": "#1C70A8",
  "mosaic": true,
  "density": "regular"
}/*EDITMODE-END*/;

function TweaksApp(){
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  React.useEffect(()=>{
    const root = document.documentElement;
    root.setAttribute('data-theme', t.theme);
    root.setAttribute('data-density', t.density);
    root.style.setProperty('--accent', t.accent);
    // soft tint derived from accent
    root.style.setProperty('--accent-soft', t.accent + '22');
    root.style.setProperty('--motif', t.mosaic ? '1' : '0');
  }, [t.theme, t.accent, t.mosaic, t.density]);

  return (
    <TweaksPanel title="עיצוב הדוח">
      <TweakSection label="כיוון עיצובי" />
      <TweakRadio label="ערכת נושא" value={t.theme}
        options={[{value:"mosaic",label:"מוזאיקה"},{value:"academic",label:"אקדמי"},{value:"civic",label:"נתונים"}]}
        onChange={v=>setTweak('theme', v)} />
      <TweakSection label="צבע מותג" />
      <TweakColor label="צבע ראשי" value={t.accent}
        options={["#1C70A8","#1CA8C4","#1C548C","#8C1C8C","#00322F"]}
        onChange={v=>setTweak('accent', v)} />
      <TweakSection label="פריסה" />
      <TweakRadio label="צפיפות" value={t.density}
        options={[{value:"compact",label:"צפוף"},{value:"regular",label:"רגיל"},{value:"comfy",label:"אוורירי"}]}
        onChange={v=>setTweak('density', v)} />
      <TweakToggle label="מוטיב מוזאיקה" value={t.mosaic}
        onChange={v=>setTweak('mosaic', v)} />
    </TweaksPanel>
  );
}
ReactDOM.createRoot(document.getElementById('tweaks-root')).render(<TweaksApp/>);
