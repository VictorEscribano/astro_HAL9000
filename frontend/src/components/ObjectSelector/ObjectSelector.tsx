import { useState, useEffect, useCallback, useRef } from "react";
import { useAppStore, SkyObject } from "../../store";
import PanelFrame from "../ui/PanelFrame";
import { api } from "../../api";

// ── Image maps ──────────────────────────────────────────────────────────────
const THUMB_IMAGES: Record<string, string> = {
  // Planets
  "Sun":     "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b4/The_Sun_by_the_Atmospheric_Imaging_Assembly_of_NASA%27s_Solar_Dynamics_Observatory_-_20100819.jpg/80px-The_Sun_by_the_Atmospheric_Imaging_Assembly_of_NASA%27s_Solar_Dynamics_Observatory_-_20100819.jpg",
  "Moon":    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e1/FullMoon2010.jpg/80px-FullMoon2010.jpg",
  "Mercury": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4a/Mercury_in_color_-_Prockter07-edit1.jpg/80px-Mercury_in_color_-_Prockter07-edit1.jpg",
  "Venus":   "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Venus_from_Mariner_10.jpg/80px-Venus_from_Mariner_10.jpg",
  "Mars":    "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/OSIRIS_Mars_true_color.jpg/80px-OSIRIS_Mars_true_color.jpg",
  "Jupiter": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2b/Jupiter_and_its_shrunken_Great_Red_Spot.jpg/80px-Jupiter_and_its_shrunken_Great_Red_Spot.jpg",
  "Saturn":  "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c7/Saturn_during_Equinox.jpg/80px-Saturn_during_Equinox.jpg",
  "Uranus":  "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Uranus2.jpg/80px-Uranus2.jpg",
  "Neptune": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/63/Neptune_-_Voyager_2_%2829347980845%29_flatten_crop.jpg/80px-Neptune_-_Voyager_2_%2829347980845%29_flatten_crop.jpg",
  // Messier DSOs
  "M1":  "https://upload.wikimedia.org/wikipedia/commons/thumb/0/00/Crab_Nebula.jpg/80px-Crab_Nebula.jpg",
  "M13": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/Messier_13_Hubble_WikiSky.jpg/80px-Messier_13_Hubble_WikiSky.jpg",
  "M16": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2b/Heic0506a.jpg/80px-Heic0506a.jpg",
  "M17": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9b/Omega_Nebula.jpg/80px-Omega_Nebula.jpg",
  "M20": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/30/Trifid.nebula.arp.750pix.jpg/80px-Trifid.nebula.arp.750pix.jpg",
  "M27": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6b/Dumbbell_nebula.jpg/80px-Dumbbell_nebula.jpg",
  "M31": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/98/Andromeda_Galaxy_%28with_h-alpha%29.jpg/80px-Andromeda_Galaxy_%28with_h-alpha%29.jpg",
  "M33": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/61/Messier_33_sRGB.jpg/80px-Messier_33_sRGB.jpg",
  "M42": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f3/Orion_Nebula_-_Hubble_2006_mosaic_18000.jpg/80px-Orion_Nebula_-_Hubble_2006_mosaic_18000.jpg",
  "M43": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f3/Orion_Nebula_-_Hubble_2006_mosaic_18000.jpg/80px-Orion_Nebula_-_Hubble_2006_mosaic_18000.jpg",
  "M44": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/25/Messier_044_2mass.jpg/80px-Messier_044_2mass.jpg",
  "M45": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Pleiades_large.jpg/80px-Pleiades_large.jpg",
  "M51": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/db/Hs-2005-12-a-large_web.jpg/80px-Hs-2005-12-a-large_web.jpg",
  "M57": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d0/Ring_Nebula.jpg/80px-Ring_Nebula.jpg",
  "M63": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/09/Messier63_-_Sunflower_Galaxy.jpg/80px-Messier63_-_Sunflower_Galaxy.jpg",
  "M64": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7f/Black_Eye_Galaxy_%28Messier_64%29.jpg/80px-Black_Eye_Galaxy_%28Messier_64%29.jpg",
  "M81": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/63/Messier_81_HST.jpg/80px-Messier_81_HST.jpg",
  "M82": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/04/M82_HST_ACS_2006-14-a-large_web.jpg/80px-M82_HST_ACS_2006-14-a-large_web.jpg",
  "M83": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/50/M83_-_Southern_Pinwheel_Galaxy_%28Hubble%29.jpg/80px-M83_-_Southern_Pinwheel_Galaxy_%28Hubble%29.jpg",
  "M87": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/eb/Messier_87_Hubble_WikiSky.jpg/80px-Messier_87_Hubble_WikiSky.jpg",
  "M101":"https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/M101_hires_STScI-PRC2006-10a.jpg/80px-M101_hires_STScI-PRC2006-10a.jpg",
  "M104":"https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/M104_ngc4594_sombrero_galaxy_hi-res.jpg/80px-M104_ngc4594_sombrero_galaxy_hi-res.jpg",
  "M106":"https://upload.wikimedia.org/wikipedia/commons/thumb/2/26/Messier_106_image_by_Spitzer_Space_Telescope.jpg/80px-Messier_106_image_by_Spitzer_Space_Telescope.jpg",
  // Named NGC
  "NGC224": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/98/Andromeda_Galaxy_%28with_h-alpha%29.jpg/80px-Andromeda_Galaxy_%28with_h-alpha%29.jpg",
  "NGC4594":"https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/M104_ngc4594_sombrero_galaxy_hi-res.jpg/80px-M104_ngc4594_sombrero_galaxy_hi-res.jpg",
  // Stars
  "Sirius":      "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ac/Sirius_A_and_B_Hubble_photo.editted.PNG/80px-Sirius_A_and_B_Hubble_photo.editted.PNG",
  "Betelgeuse":  "https://upload.wikimedia.org/wikipedia/commons/thumb/6/60/Betelgeuse_star_%28Hubble%29.jpg/80px-Betelgeuse_star_%28Hubble%29.jpg",
  "Rigel":       "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2f/Rigel_2.jpg/80px-Rigel_2.jpg",
  "Vega":        "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f4/Vega_HST.jpg/80px-Vega_HST.jpg",
  "Arcturus":    "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6f/Arcturus.jpg/80px-Arcturus.jpg",
  "Antares":     "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fa/Antares_and_neighbourhood.jpg/80px-Antares_and_neighbourhood.jpg",
  "Aldebaran":   "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b4/Aldebaran-crop.jpg/80px-Aldebaran-crop.jpg",
  "Canopus":     "https://upload.wikimedia.org/wikipedia/commons/thumb/5/56/Canopus.jpg/80px-Canopus.jpg",
  "Capella":     "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e6/Capella_star.jpg/80px-Capella_star.jpg",
  "Deneb":       "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fa/Deneb.jpg/80px-Deneb.jpg",
  // Satellites
  "ISS":         "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/ISS_2_with_Space_Shuttle_attached.jpg/80px-ISS_2_with_Space_Shuttle_attached.jpg",
  "Hubble":      "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3f/HST-SM4.jpeg/80px-HST-SM4.jpeg",
};

type Tab = "TONIGHT" | "DSO" | "STARS" | "PLANETS" | "SATELLITES";

interface CatalogEntry {
  id: string;
  name: string;
  catalog_id?: string;
  object_type: string;
  ra_h?: number;
  dec_deg?: number;
  magnitude?: number;
  angular_size_arcmin?: number;
  alt_deg?: number;
  az_deg?: number;
  note?: string;
  norad_id?: number;
  spectral?: string;
}

const TYPE_SHORT: Record<string, string> = {
  Planet: "PLANET", Gx: "GAL", OC: "CLUSTER", Nb: "NEBULA", GC: "GLOB",
  Pl: "PNEB", Satellite: "SAT", Star: "STAR", DSO: "DSO",
  PAY: "SAT", "R/B": "RKT", DEB: "DEB",
};

function ObjectThumb({
  obj, selected, onSelect,
}: { obj: CatalogEntry; selected: boolean; onSelect: (o: CatalogEntry) => void }) {
  const key = obj.catalog_id?.replace("NGC0", "NGC").replace(/^NGC0*/, "NGC") ?? obj.name.split("(")[0].trim();
  const img = THUMB_IMAGES[key] ?? THUMB_IMAGES[obj.name.split("(")[0].trim()];
  const typeLabel = TYPE_SHORT[obj.object_type] ?? "OBJ";

  return (
    <button
      onClick={() => onSelect(obj)}
      className={`relative flex flex-col items-center gap-1 p-1.5 rounded transition-all duration-150 border
        ${selected
          ? "border-accent-red/70 bg-accent-red/10"
          : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/[0.15]"
        }`}
    >
      <div className="w-full aspect-square overflow-hidden rounded bg-white/[0.03] relative">
        {img ? (
          <img src={img} alt={obj.name} className="w-full h-full object-cover"
            style={{ filter: "grayscale(40%) brightness(0.7)" }} />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <span className="text-white/10 text-lg">◎</span>
          </div>
        )}
        {selected && <div className="absolute inset-0 border border-accent-red/50" />}
      </div>
      <div className="text-[calc(8px*var(--fs))] font-mono text-text/80 truncate w-full text-center leading-tight">
        {obj.catalog_id ?? obj.name.split("(")[0].trim()}
      </div>
      <div className="text-[calc(7px*var(--fs))] font-mono text-dim">{typeLabel}</div>
      {obj.magnitude != null && (
        <div className="text-[calc(7px*var(--fs))] font-mono text-dim/60">m={obj.magnitude.toFixed(1)}</div>
      )}
    </button>
  );
}

export default function ObjectSelector() {
  const { skyObjects, selectedTarget, setSelectedTarget, setViewMode, setInfoCard, setGroundTrack } = useAppStore();
  const [tab, setTab] = useState<Tab>("TONIGHT");
  const [search, setSearch] = useState("");
  const [catalogResults, setCatalogResults] = useState<CatalogEntry[]>([]);
  const [catalogTotal, setCatalogTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const searchRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const LIMIT = 80;

  const TABS: Tab[] = ["TONIGHT", "DSO", "STARS", "PLANETS", "SATELLITES"];

  // Fetch catalog for non-TONIGHT tabs
  const fetchCatalog = useCallback(async (q: string, currentTab: Tab, off: number) => {
    if (currentTab === "TONIGHT") return;
    setLoading(true);
    try {
      let newResults: CatalogEntry[] = [];
      let total = 0;

      if (currentTab === "SATELLITES") {
        const res = await api.satelliteCatalog(q, LIMIT, off, "PAYLOAD");
        newResults = (res.results ?? []).map((s: Record<string, unknown>) => ({
          id: String(s.norad_id),
          name: String(s.name),
          catalog_id: String(s.norad_id),
          object_type: "Satellite",
          norad_id: Number(s.norad_id),
          magnitude: undefined,
        }));
        total = res.total ?? 0;
      } else {
        const typeMap: Record<Tab, string> = {
          DSO: "dso", STARS: "star", PLANETS: "planet",
          TONIGHT: "all", SATELLITES: "all",
        };
        const res = await api.catalogSearch(q, typeMap[currentTab] ?? "all", LIMIT, off);
        newResults = res.results ?? [];
        total = res.total ?? 0;
      }

      // Append on loadMore (off > 0), replace on fresh search
      if (off === 0) {
        setCatalogResults(newResults);
      } else {
        setCatalogResults(prev => [...prev, ...newResults]);
      }
      setCatalogTotal(total);
    } catch (err) {
      console.error("[ObjectSelector] catalog fetch error:", err);
      if (off === 0) setCatalogResults([]);
    }
    setLoading(false);
  }, []);

  // Debounced search
  useEffect(() => {
    if (tab === "TONIGHT") return;
    setOffset(0);
    if (searchRef.current) clearTimeout(searchRef.current);
    searchRef.current = setTimeout(() => fetchCatalog(search, tab, 0), 300);
  }, [search, tab, fetchCatalog]);

  // Load on tab change
  useEffect(() => {
    if (tab !== "TONIGHT") {
      setSearch("");
      setOffset(0);
      fetchCatalog("", tab, 0);
    }
  }, [tab, fetchCatalog]);

  // Load more
  const loadMore = () => {
    const next = offset + LIMIT;
    setOffset(next);
    fetchCatalog(search, tab, next);
  };

  async function handleSelect(obj: CatalogEntry) {
    if (obj.object_type === "Satellite" || obj.norad_id) {
      const norad = obj.norad_id ?? parseInt(obj.id);
      setSelectedTarget({ name: obj.name, norad_id: norad, type: "satellite" });
      setInfoCard({ name: obj.name, object_type: "Satellite" });
      setViewMode("earthMap");
      // Fetch ground track
      try {
        const track = await api.groundTrack(norad);
        if (Array.isArray(track)) setGroundTrack(track);
      } catch { /* ignore */ }
    } else {
      setSelectedTarget({
        name: obj.catalog_id ?? obj.name,
        ra_h: obj.ra_h,
        dec_deg: obj.dec_deg,
        type: obj.object_type === "Planet" ? "planet" : "dso",
      });
      setViewMode("skyChart");
      setInfoCard({
        name: obj.name,
        catalog_id: obj.catalog_id,
        object_type: obj.object_type,
        magnitude: obj.magnitude,
        angular_size_arcmin: obj.angular_size_arcmin,
        alt_deg: obj.alt_deg,
        az_deg: obj.az_deg,
        note: obj.note,
      });
    }
  }

  // For TONIGHT tab, use skyObjects from store
  const tonightItems: CatalogEntry[] = skyObjects
    .filter((o) => !search || o.name.toLowerCase().includes(search.toLowerCase())
      || (o.catalog_id ?? "").toLowerCase().includes(search.toLowerCase()))
    .map((o) => ({
      id: o.catalog_id ?? o.name,
      name: o.name,
      catalog_id: o.catalog_id,
      object_type: o.object_type,
      ra_h: o.ra_h,
      dec_deg: o.dec_deg,
      magnitude: o.magnitude,
      angular_size_arcmin: o.angular_size_arcmin,
      alt_deg: o.alt_deg,
      az_deg: o.az_deg,
      note: o.note,
    }));

  const displayItems = tab === "TONIGHT" ? tonightItems : catalogResults;
  const displayTotal = tab === "TONIGHT" ? tonightItems.length : catalogTotal;

  return (
    <PanelFrame title="OBJECT SELECTOR" className="h-full flex flex-col" accent="red">
      <div className="flex flex-col h-full">
        {/* Category tabs */}
        <div className="flex border-b border-white/[0.06] shrink-0 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 py-1.5 text-[calc(8px*var(--fs))] font-mono uppercase tracking-wider transition-colors whitespace-nowrap px-1
                ${tab === t ? "bg-accent-red text-bg font-bold" : "text-dim hover:text-text"}`}
            >
              {t === "TONIGHT" ? "◉ NOW" : t === "SATELLITES" ? "⊹ SAT" :
               t === "STARS" ? "★" : t === "PLANETS" ? "⊕" : t}
            </button>
          ))}
        </div>

        {/* Grid */}
        <div className="flex-1 min-h-0 overflow-y-auto p-2">
          {loading && (
            <div className="text-center text-dim text-[calc(9px*var(--fs))] font-mono py-4 tracking-widest animate-pulse">
              LOADING…
            </div>
          )}
          {!loading && displayItems.length === 0 ? (
            <div className="text-center text-dim text-[calc(9px*var(--fs))] font-mono py-8 tracking-widest">
              {tab === "TONIGHT" && skyObjects.length === 0 ? "LOADING…" : "NO OBJECTS"}
            </div>
          ) : (
            <>
              <div className="grid grid-cols-4 gap-1.5">
                {displayItems.map((obj) => (
                  <ObjectThumb
                    key={`${obj.id}-${obj.name}`}
                    obj={obj}
                    selected={
                      selectedTarget?.name === obj.name ||
                      selectedTarget?.name === obj.catalog_id ||
                      (obj.norad_id != null && selectedTarget?.norad_id === obj.norad_id)
                    }
                    onSelect={handleSelect}
                  />
                ))}
              </div>
              {/* Load more */}
              {tab !== "TONIGHT" && offset + LIMIT < catalogTotal && (
                <button
                  onClick={loadMore}
                  className="w-full mt-2 py-1.5 text-[calc(8px*var(--fs))] font-mono text-dim hover:text-text
                             border border-white/[0.06] rounded tracking-widest transition-colors"
                >
                  LOAD MORE ({catalogTotal - offset - LIMIT} remaining)
                </button>
              )}
            </>
          )}
        </div>

        {/* Footer: search + count */}
        <div className="shrink-0 border-t border-white/[0.06] px-2 py-1.5 flex items-center gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={tab === "TONIGHT" ? "FILTER…" : "SEARCH CATALOG…"}
            className="flex-1 bg-white/[0.04] border border-white/[0.06] rounded px-2 py-1
                       text-[calc(9px*var(--fs))] font-mono text-text placeholder-dim focus:outline-none
                       focus:border-accent-red/40"
          />
          <span className="text-[calc(8px*var(--fs))] font-mono text-dim shrink-0">
            {displayTotal.toLocaleString()} OBJ
          </span>
        </div>
      </div>
    </PanelFrame>
  );
}
