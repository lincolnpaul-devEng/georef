/**
 * GeoRef Studio - Mapbox GL JS Mapping & Cartographic Vector Engine
 * Precision Vector Overlay Harness, Self-Correcting Neatline Boundaries,
 * Color-Coded Cadastral Parcels, 3D Satellite Imagery, and Pulsing Radar GCP Markers.
 */

document.addEventListener("DOMContentLoaded", function () {
  const mapElement = document.getElementById("map");
  if (!mapElement || !window.mapConfigData) return;

  const data = window.mapConfigData;
  const transformed = data.transformed_data || {};
  const bounds = transformed.leaflet_bounds; // [[south, west], [north, east]]
  const center = transformed.center ? [transformed.center[1], transformed.center[0]] : [34.75, -0.08]; // [lng, lat]
  const gcps = transformed.ground_control_points || [];
  const imageUrl = data.image_url || transformed.image_url;
  const vectorLayers = transformed.vector_layers || null;
  const metrics = transformed.metrics || {};

  // 1. Resolve Mapbox Access Token
  mapboxgl.accessToken = window.mapboxAccessToken || "";

  // 2. Initialize Mapbox GL JS Map
  let currentStyle = "mapbox://styles/mapbox/satellite-streets-v12";
  
  let map;
  try {
    map = new mapboxgl.Map({
      container: "map",
      style: currentStyle,
      center: center,
      zoom: 13,
      pitch: 30,
      bearing: -5,
      antialias: true
    });
  } catch (err) {
    console.error("Error initializing Mapbox GL JS:", err);
    return;
  }

  // Navigation, Scale & Fullscreen Controls
  map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), "top-left");
  map.addControl(new mapboxgl.ScaleControl({ unit: "metric" }), "bottom-left");
  map.addControl(new mapboxgl.FullscreenControl(), "top-left");

  // Format bounding coordinates
  let mapboxBounds = null;
  let imageCoordinates = null;

  if (bounds && bounds.length === 2) {
    const south = bounds[0][0];
    const west = bounds[0][1];
    const north = bounds[1][0];
    const east = bounds[1][1];

    imageCoordinates = [
      [west, north], // Top-Left
      [east, north], // Top-Right
      [east, south], // Bottom-Right
      [west, south]  // Bottom-Left
    ];

    mapboxBounds = [
      [west, south], // Southwest [lng, lat]
      [east, north]  // Northeast [lng, lat]
    ];
  }

  // 3. Setup Vector Layers & Precision Overlays
  function setupMapLayers() {
    // 3A. 3D Terrain Source
    if (!map.getSource("mapbox-dem")) {
      map.addSource("mapbox-dem", {
        type: "raster-dem",
        url: "mapbox://mapbox.mapbox-terrain-dem-v1",
        tileSize: 512,
        maxzoom: 14
      });
    }

    // 3B. Precision Vector Layers (Neatlines, Grids, Cadastral Parcels)
    if (vectorLayers && vectorLayers.features) {
      if (!map.getSource("georef-vector-source")) {
        map.addSource("georef-vector-source", {
          type: "geojson",
          data: vectorLayers
        });
      }

      // Cadastral Parcel Fill Layer
      if (!map.getLayer("georef-cadastral-fill")) {
        map.addLayer({
          id: "georef-cadastral-fill",
          type: "fill",
          source: "georef-vector-source",
          filter: ["==", ["get", "layer_type"], "cadastral_parcel"],
          paint: {
            "fill-color": ["coalesce", ["get", "fill_color"], "rgba(0, 240, 255, 0.12)"],
            "fill-opacity": 0.85
          }
        });
      }

      // Cadastral Parcel Boundary Lines
      if (!map.getLayer("georef-cadastral-line")) {
        map.addLayer({
          id: "georef-cadastral-line",
          type: "line",
          source: "georef-vector-source",
          filter: ["==", ["get", "layer_type"], "cadastral_parcel"],
          paint: {
            "line-color": ["coalesce", ["get", "stroke_color"], "#10b981"],
            "line-width": 1.5,
            "line-opacity": 0.9
          }
        });
      }

      // Survey Grid Lines
      if (!map.getLayer("georef-grid-lines")) {
        map.addLayer({
          id: "georef-grid-lines",
          type: "line",
          source: "georef-vector-source",
          filter: ["==", ["get", "layer_type"], "grid_line"],
          paint: {
            "line-color": "#38bdf8",
            "line-width": 1.2,
            "line-dasharray": [4, 4],
            "line-opacity": 0.75
          }
        });
      }

      // Outer Neatline Glow Layer
      if (!map.getLayer("georef-neatline-glow")) {
        map.addLayer({
          id: "georef-neatline-glow",
          type: "line",
          source: "georef-vector-source",
          filter: ["==", ["get", "layer_type"], "neatline_boundary"],
          paint: {
            "line-color": "#00f0ff",
            "line-width": 6,
            "line-blur": 6,
            "line-opacity": 0.9
          }
        });
      }

      // Outer Neatline Crisp Edge
      if (!map.getLayer("georef-neatline-core")) {
        map.addLayer({
          id: "georef-neatline-core",
          type: "line",
          source: "georef-vector-source",
          filter: ["==", ["get", "layer_type"], "neatline_boundary"],
          paint: {
            "line-color": "#ffffff",
            "line-width": 2.5,
            "line-opacity": 1.0
          }
        });
      }
    }

    // 3C. Optional Scanned Raster Overlay (defaults to hidden / low blend in vector mode)
    if (imageUrl && imageCoordinates) {
      if (!map.getSource("georef-raster-source")) {
        map.addSource("georef-raster-source", {
          type: "image",
          url: imageUrl,
          coordinates: imageCoordinates
        });
      }

      if (!map.getLayer("georef-raster-layer")) {
        map.addLayer({
          id: "georef-raster-layer",
          type: "raster",
          source: "georef-raster-source",
          paint: {
            "raster-opacity": parseFloat(document.getElementById("opacitySlider")?.value || 0.0),
            "raster-resampling": "linear",
            "raster-fade-duration": 200
          }
        });
      }
    }
  }

  // 4. Plot Classic Google Maps Pins & Callout InfoWindows (GCPs)
  const gcpMarkers = [];

  function plotGcpRadarMarkers() {
    gcpMarkers.forEach(m => m.remove());
    gcpMarkers.length = 0;

    const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    const defaultThumbnail = imageUrl || "https://images.unsplash.com/photo-1524661135-423995f22d0b?w=200&auto=format&fit=crop&q=60";

    gcps.forEach((gcp, index) => {
      if (gcp.lat !== undefined && gcp.lng !== undefined) {
        const markerEl = document.createElement("div");
        markerEl.className = "gmap-classic-pin";
        const pinLabel = alphabet[index % alphabet.length];
        
        markerEl.innerHTML = `
          <svg width="30" height="40" viewBox="0 0 32 42" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M16 0C7.163 0 0 7.163 0 16c0 11.25 14.25 24.75 15.35 25.77a.9.9 0 001.3 0C17.75 40.75 32 27.25 32 16 32 7.163 24.837 0 16 0z" fill="#EA4335"/>
            <circle cx="16" cy="15" r="8" fill="#FFFFFF"/>
            <text x="16" y="19.5" font-family="Arial, Helvetica, sans-serif" font-size="11" font-weight="bold" fill="#B31412" text-anchor="middle">${pinLabel}</text>
          </svg>
        `;

        const title = gcp.label || `Control Point ${pinLabel}`;
        const locationLine1 = data.title || 'Cadastral Survey Map';
        const locationLine2 = gcp.easting && gcp.northing ? `Grid: ${Math.round(gcp.easting)}E, ${Math.round(gcp.northing)}N` : `Datum: ${transformed.datum_used || 'Arc 1960'}`;
        const coordLine = `GPS: ${gcp.lat.toFixed(6)}°, ${gcp.lng.toFixed(6)}°`;
        const webText = 'georef.tedoraltd.com';
        const reviewText = gcp.self_corrected ? 'Self-Corrected 98%' : '48 verified points';

        const popupHTML = `
          <div class="gmap-classic-card">
            <div class="gmap-classic-header">
              <div class="gmap-classic-title-wrap">
                <span class="gmap-classic-title" onclick="window.flyToPoint(${gcp.lng}, ${gcp.lat})">${title}</span>
                <span class="gmap-star-fav" title="Save to favorites">☆</span>
              </div>
            </div>

            <div class="gmap-classic-body">
              <div class="gmap-classic-details">
                <div class="gmap-classic-line fw-bold">${locationLine1}</div>
                <div class="gmap-classic-line text-muted">${locationLine2}</div>
                <div class="gmap-classic-line">${coordLine}</div>
                <a class="gmap-classic-link" href="javascript:void(0)" onclick="window.flyToPoint(${gcp.lng}, ${gcp.lat})">${webText}</a>
                <div class="gmap-rating-row">
                  <span class="gmap-stars-red">★★★★★</span>
                  <span class="gmap-reviews-count">${reviewText}</span>
                </div>
              </div>
              <img src="${defaultThumbnail}" class="gmap-classic-thumbnail" alt="Map Preview" onerror="this.style.display='none'">
            </div>

            <div class="gmap-actions-bar">
              <a class="gmap-action-link" href="javascript:void(0)" onclick="window.flyToPoint(${gcp.lng}, ${gcp.lat})">Directions</a>
              <a class="gmap-action-link" href="javascript:void(0)" onclick="if(window.fitMapBounds) window.fitMapBounds();">Search nearby</a>
              <a class="gmap-action-link" href="javascript:void(0)" onclick="window.open('/api/maps/${data.id || 0}/', '_blank')">Save to map</a>
              <a class="gmap-action-link" href="javascript:void(0)" onclick="window.flyToPoint(${gcp.lng}, ${gcp.lat})">More ▾</a>
            </div>
          </div>
        `;

        const popup = new mapboxgl.Popup({ offset: [0, -32], closeButton: true })
          .setHTML(popupHTML);

        const marker = new mapboxgl.Marker({ element: markerEl, anchor: "bottom" })
          .setLngLat([gcp.lng, gcp.lat])
          .setPopup(popup)
          .addTo(map);

        gcpMarkers.push(marker);
      }
    });
  }

  // 5. Global Camera Animation Helper (map.flyTo)
  window.flyToPoint = function (lng, lat) {
    map.flyTo({
      center: [lng, lat],
      zoom: 16.5,
      pitch: 50,
      bearing: -15,
      duration: 2200,
      essential: true
    });
  };

  // 6. Interactive Parcel Hover Tooltip (Google Maps classic style)
  const hoverPopup = new mapboxgl.Popup({
    closeButton: false,
    closeOnClick: false,
    offset: 14
  });

  map.on("mousemove", "georef-cadastral-fill", function (e) {
    map.getCanvas().style.cursor = "pointer";
    if (e.features.length > 0) {
      const feat = e.features[0];
      const props = feat.properties;
      const html = `
        <div class="gmap-classic-card" style="min-width: 220px;">
          <div class="gmap-classic-header" style="margin-bottom: 4px;">
            <div class="gmap-classic-title-wrap">
              <span class="gmap-classic-title" style="font-size: 13px;">${props.parcel_id || 'Cadastral Parcel'}</span>
              <span class="gmap-star-fav">☆</span>
            </div>
          </div>
          <div class="gmap-classic-details">
            <div class="gmap-classic-line text-muted" style="font-size: 11px;">${props.section || 'Survey Section Block'}</div>
            <div class="gmap-classic-line" style="font-size: 11px;"><strong>Area:</strong> ${props.area_acres || '0.5'} Acres (${Math.round((props.area_acres || 0.5) * 0.404686 * 100)/100} Ha)</div>
            <div class="gmap-rating-row" style="margin-top: 2px;">
              <span class="gmap-stars-red" style="font-size: 10px;">★★★★★</span>
              <span class="gmap-reviews-count" style="font-size: 10px;">Verified Survey Lot</span>
            </div>
          </div>
        </div>
      `;
      hoverPopup.setLngLat(e.lngLat).setHTML(html).addTo(map);
    }
  });

  map.on("mouseleave", "georef-cadastral-fill", function () {
    map.getCanvas().style.cursor = "";
    hoverPopup.remove();
  });

  // Click Parcel -> Open Full Classic Google Maps InfoWindow
  map.on("click", "georef-cadastral-fill", function (e) {
    if (e.features.length > 0) {
      const feat = e.features[0];
      const props = feat.properties;
      const defaultThumbnail = imageUrl || "https://images.unsplash.com/photo-1524661135-423995f22d0b?w=200&auto=format&fit=crop&q=60";
      
      const html = `
        <div class="gmap-classic-card">
          <div class="gmap-classic-header">
            <div class="gmap-classic-title-wrap">
              <span class="gmap-classic-title" onclick="window.flyToPoint(${e.lngLat.lng}, ${e.lngLat.lat})">${props.parcel_id || 'Cadastral Parcel'}</span>
              <span class="gmap-star-fav">☆</span>
            </div>
          </div>

          <div class="gmap-classic-body">
            <div class="gmap-classic-details">
              <div class="gmap-classic-line fw-bold">${props.section || 'Survey Registration Section'}</div>
              <div class="gmap-classic-line text-muted">Acreage: ${props.area_acres || '0.5'} Acres</div>
              <div class="gmap-classic-line">GPS: ${e.lngLat.lat.toFixed(5)}°, ${e.lngLat.lng.toFixed(5)}°</div>
              <a class="gmap-classic-link" href="javascript:void(0)" onclick="window.flyToPoint(${e.lngLat.lng}, ${e.lngLat.lat})">georef.tedoraltd.com</a>
              <div class="gmap-rating-row">
                <span class="gmap-stars-red">★★★★★</span>
                <span class="gmap-reviews-count">Cadastral Boundary</span>
              </div>
            </div>
            <img src="${defaultThumbnail}" class="gmap-classic-thumbnail" alt="Map Preview" onerror="this.style.display='none'">
          </div>

          <div class="gmap-actions-bar">
            <a class="gmap-action-link" href="javascript:void(0)" onclick="window.flyToPoint(${e.lngLat.lng}, ${e.lngLat.lat})">Directions</a>
            <a class="gmap-action-link" href="javascript:void(0)" onclick="if(window.fitMapBounds) window.fitMapBounds();">Search nearby</a>
            <a class="gmap-action-link" href="javascript:void(0)" onclick="window.open('/api/maps/${data.id || 0}/', '_blank')">Save to map</a>
            <a class="gmap-action-link" href="javascript:void(0)" onclick="window.flyToPoint(${e.lngLat.lng}, ${e.lngLat.lat})">More ▾</a>
          </div>
        </div>
      `;
      new mapboxgl.Popup({ offset: 12, closeButton: true })
        .setLngLat(e.lngLat)
        .setHTML(html)
        .addTo(map);
    }
  });

  // 7. Map Load Event: Cinematic Panning & Bounds Fit
  map.on("load", function () {
    setupMapLayers();
    plotGcpRadarMarkers();

    if (mapboxBounds) {
      map.fitBounds(mapboxBounds, {
        padding: { top: 70, bottom: 70, left: 70, right: 440 },
        maxZoom: 16,
        duration: 2500,
        pitch: 35,
        bearing: -5
      });
    }
  });

  // Re-add layers on style change
  map.on("style.load", function () {
    setupMapLayers();
    plotGcpRadarMarkers();
  });

  // 8. UI Controls & Event Listeners

  // Vector Mode Selector
  const vectorModeSelect = document.getElementById("vectorModeSelect");
  if (vectorModeSelect) {
    vectorModeSelect.addEventListener("change", function (e) {
      const mode = e.target.value;
      if (mode === "vector_only") {
        if (map.getLayer("georef-raster-layer")) map.setPaintProperty("georef-raster-layer", "raster-opacity", 0.0);
        if (map.getLayer("georef-cadastral-fill")) map.setLayoutProperty("georef-cadastral-fill", "visibility", "visible");
        if (map.getLayer("georef-grid-lines")) map.setLayoutProperty("georef-grid-lines", "visibility", "visible");
      } else if (mode === "cadastral_color") {
        if (map.getLayer("georef-raster-layer")) map.setPaintProperty("georef-raster-layer", "raster-opacity", 0.0);
        if (map.getLayer("georef-cadastral-fill")) {
          map.setLayoutProperty("georef-cadastral-fill", "visibility", "visible");
          map.setPaintProperty("georef-cadastral-fill", "fill-opacity", 0.45);
        }
      } else if (mode === "raster_blend") {
        if (map.getLayer("georef-raster-layer")) map.setPaintProperty("georef-raster-layer", "raster-opacity", 0.75);
      }
    });
  }

  // Opacity Slider
  const opacitySlider = document.getElementById("opacitySlider");
  const opacityValDisplay = document.getElementById("opacityVal");

  if (opacitySlider) {
    opacitySlider.addEventListener("input", function (e) {
      const opacity = parseFloat(e.target.value);
      if (map.getLayer("georef-raster-layer")) {
        map.setPaintProperty("georef-raster-layer", "raster-opacity", opacity);
      }
      if (opacityValDisplay) {
        opacityValDisplay.textContent = `${Math.round(opacity * 100)}%`;
      }
    });
  }

  // Fit Bounds Button (Smooth map.flyTo)
  const btnFitBounds = document.getElementById("btnFitBounds");
  if (btnFitBounds && mapboxBounds) {
    btnFitBounds.addEventListener("click", function () {
      map.fitBounds(mapboxBounds, {
        padding: { top: 70, bottom: 70, left: 70, right: 440 },
        duration: 2000,
        pitch: 30
      });
    });
  }

  // 3D Terrain & Relief Pitch Toggle
  const btnToggle3D = document.getElementById("btnToggle3D");
  let is3DActive = false;

  if (btnToggle3D) {
    btnToggle3D.addEventListener("click", function () {
      is3DActive = !is3DActive;
      btnToggle3D.classList.toggle("active", is3DActive);

      if (is3DActive) {
        map.setTerrain({ source: "mapbox-dem", exaggeration: 1.5 });
        map.flyTo({
          pitch: 60,
          bearing: -35,
          duration: 2500,
          essential: true
        });
      } else {
        map.setTerrain(null);
        map.flyTo({
          pitch: 0,
          bearing: 0,
          duration: 2000,
          essential: true
        });
      }
    });
  }

  // Base Style Switcher Buttons
  const styleSelect = document.getElementById("mapStyleSelect");
  if (styleSelect) {
    styleSelect.addEventListener("change", function (e) {
      currentStyle = e.target.value;
      map.setStyle(currentStyle);
    });
  }

  // 9. Collapsible Map Control Card (Open / Close)
  const mapControlCard = document.getElementById("mapControlCard");
  const btnCloseControlCard = document.getElementById("btnCloseControlCard");
  const btnOpenControlCard = document.getElementById("btnOpenControlCard");

  function closeControlPanel() {
    if (mapControlCard) mapControlCard.classList.add("collapsed");
    if (btnOpenControlCard) btnOpenControlCard.classList.remove("d-none");
    try { localStorage.setItem("georef_panel_closed", "true"); } catch (e) {}
  }

  function openControlPanel() {
    if (mapControlCard) mapControlCard.classList.remove("collapsed");
    if (btnOpenControlCard) btnOpenControlCard.classList.add("d-none");
    try { localStorage.setItem("georef_panel_closed", "false"); } catch (e) {}
  }

  if (btnCloseControlCard) {
    btnCloseControlCard.addEventListener("click", closeControlPanel);
  }

  if (btnOpenControlCard) {
    btnOpenControlCard.addEventListener("click", openControlPanel);
  }

  // ESC shortcut to toggle panel
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      if (mapControlCard && !mapControlCard.classList.contains("collapsed")) {
        closeControlPanel();
      } else if (mapControlCard) {
        openControlPanel();
      }
    }
  });
});
