import { useEffect, useState } from "react";
import { MapContainer, TileLayer, Polyline, Marker, Popup, Polygon, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useAppStore } from "../../store";
import { api } from "../../api";

// Fix default icon
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl:       "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl:     "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const OBS_ICON = L.divIcon({
  className: "",
  html: `<div style="width:10px;height:10px;border-radius:50%;background:#3BA7FF;border:2px solid #fff;box-shadow:0 0 8px #3BA7FF"></div>`,
  iconAnchor: [5, 5],
});

const SAT_ICON = L.divIcon({
  className: "",
  html: `<div style="width:8px;height:8px;border-radius:50%;background:#34d399;border:2px solid #fff;box-shadow:0 0 6px #34d399"></div>`,
  iconAnchor: [4, 4],
});

interface TrackPoint {
  lat: number;
  lng: number;
  visible?: boolean;
  el_deg?: number;
}

function FlyToObserver() {
  const map = useMap();
  const { observer } = useAppStore();
  useEffect(() => {
    map.setView([observer.lat, observer.lng], 3);
  }, [observer.lat, observer.lng]);
  return null;
}

// Split track into segments by visibility AND antimeridian crossings
function splitTrack(track: TrackPoint[]): { positions: [number, number][]; visible: boolean }[] {
  if (track.length === 0) return [];
  const segments: { positions: [number, number][]; visible: boolean }[] = [];
  let cur: { positions: [number, number][]; visible: boolean } = {
    positions: [[track[0].lat, track[0].lng]],
    visible: !!track[0].visible,
  };
  for (let i = 1; i < track.length; i++) {
    const pt = track[i];
    const prevLng = track[i - 1].lng;
    // Antimeridian crossing: split segment to avoid wrapping line across map
    const antimeridian = Math.abs(pt.lng - prevLng) > 150;
    const visibilityChange = !!pt.visible !== cur.visible;
    if (antimeridian || visibilityChange) {
      if (cur.positions.length > 1) segments.push(cur);
      cur = { positions: [[pt.lat, pt.lng]], visible: !!pt.visible };
    } else {
      cur.positions.push([pt.lat, pt.lng]);
    }
  }
  if (cur.positions.length > 1) segments.push(cur);
  return segments;
}

export default function EarthMap() {
  const { observer, groundTrack, selectedTarget } = useAppStore();
  const [footprint, setFootprint] = useState<[number, number][]>([]);

  const darkTiles = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
  const attribution = '&copy; <a href="https://carto.com/">CARTO</a>';

  // Fetch footprint only for satellite targets
  useEffect(() => {
    if (!selectedTarget?.norad_id || selectedTarget.type !== "satellite") {
      setFootprint([]);
      return;
    }
    api.satelliteFootprint(selectedTarget.norad_id)
      .then((pts: { lat: number; lng: number }[]) =>
        setFootprint(pts.map((p) => [p.lat, p.lng] as [number, number]))
      )
      .catch(() => setFootprint([]));
  }, [selectedTarget?.norad_id, selectedTarget?.type]);

  const isSatelliteMode = selectedTarget?.type === "satellite";
  const segments = isSatelliteMode ? splitTrack(groundTrack as TrackPoint[]) : [];

  // Current satellite position marker — only show for satellite targets
  const currentPos = isSatelliteMode
    ? ((groundTrack as TrackPoint[]).find((p) => p.visible) ?? groundTrack[0])
    : null;

  return (
    <MapContainer
      center={[observer.lat, observer.lng]}
      zoom={3}
      style={{ width: "100%", height: "100%", background: "#050507" }}
      zoomControl={true}
    >
      <TileLayer url={darkTiles} attribution={attribution} />
      <FlyToObserver />

      {/* Observer marker */}
      <Marker position={[observer.lat, observer.lng]} icon={OBS_ICON}>
        <Popup>
          <span style={{ color: "#000", fontFamily: "monospace", fontSize: 12 }}>
            {observer.name}<br />
            {observer.lat.toFixed(4)}°N {observer.lng.toFixed(4)}°E
          </span>
        </Popup>
      </Marker>

      {/* Full ground track — non-visible segments (dimmer) */}
      {segments.filter((s) => !s.visible).map((seg, i) => (
        <Polyline
          key={`non-vis-${i}`}
          positions={seg.positions}
          color="#3BA7FF"
          weight={1}
          opacity={0.25}
        />
      ))}

      {/* Visible arc (from observer's horizon) — highlighted */}
      {segments.filter((s) => s.visible).map((seg, i) => (
        <Polyline
          key={`vis-${i}`}
          positions={seg.positions}
          color="#34d399"
          weight={2.5}
          opacity={0.9}
        />
      ))}

      {/* Visibility footprint */}
      {footprint.length > 3 && (
        <Polygon
          positions={footprint}
          pathOptions={{
            color: "#3BA7FF",
            fillColor: "#3BA7FF",
            fillOpacity: 0.06,
            weight: 1,
            opacity: 0.35,
            dashArray: "4 6",
          }}
        />
      )}

      {/* Current satellite position marker */}
      {currentPos && (
        <Marker position={[currentPos.lat, currentPos.lng]} icon={SAT_ICON}>
          <Popup>
            <span style={{ color: "#000", fontFamily: "monospace", fontSize: 12 }}>
              {selectedTarget?.name ?? "Satellite"}<br />
              {currentPos.lat.toFixed(3)}°N {currentPos.lng.toFixed(3)}°E
            </span>
          </Popup>
        </Marker>
      )}
    </MapContainer>
  );
}
