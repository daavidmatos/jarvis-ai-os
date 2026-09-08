figma.showUI(__html__, { width: 340, height: 280, themeColors: true });

const ACTIONS = [
  "inspect_document", "create_rectangle", "create_text", "create_frame",
  "create_landing_page", "set_text", "set_geometry", "set_fill", "delete_node", "undo"
];

function hexToRgb(hex) {
  const value = String(hex || "#111111").replace("#", "");
  const n = parseInt(value, 16);
  return { r: ((n >> 16) & 255) / 255, g: ((n >> 8) & 255) / 255, b: (n & 255) / 255 };
}

function solid(hex) {
  return [{ type: "SOLID", color: hexToRgb(hex) }];
}

async function ensureFonts() {
  await figma.loadFontAsync({ family: "Inter", style: "Regular" });
  await figma.loadFontAsync({ family: "Inter", style: "Bold" });
}

async function makeText(text, x, y, size, weight, color, name) {
  await ensureFonts();
  const node = figma.createText();
  node.fontName = { family: "Inter", style: weight === "bold" ? "Bold" : "Regular" };
  node.characters = String(text || "");
  node.fontSize = Number(size || 32);
  node.textAutoResize = "WIDTH_AND_HEIGHT";
  node.x = Number(x || 0);
  node.y = Number(y || 0);
  node.fills = solid(color || "#111111");
  if (name) node.name = name;
  return node;
}

async function findNode(args) {
  if (args.node_id) {
    const node = await figma.getNodeByIdAsync(String(args.node_id));
    if (node) return node;
  }
  if (args.node_name) {
    const wanted = String(args.node_name).toLowerCase();
    const exact = figma.currentPage.findOne(n => String(n.name || "").toLowerCase() === wanted);
    if (exact) return exact;
  }
  return null;
}

function nodeSnapshot(node) {
  const base = {
    id: node.id,
    name: node.name,
    type: node.type,
    visible: node.visible !== false
  };
  if ("x" in node) base.x = node.x;
  if ("y" in node) base.y = node.y;
  if ("width" in node) base.width = node.width;
  if ("height" in node) base.height = node.height;
  if (node.type === "TEXT") base.text = node.characters.slice(0, 1000);
  return base;
}

function getState() {
  const children = figma.currentPage.children.slice(0, 120).map(nodeSnapshot);
  const selection = figma.currentPage.selection.map(nodeSnapshot);
  return {
    adapter: { name: "jarvis-figma", write: true, version: "0.2.0", actions: ACTIONS },
    file_name: figma.root.name,
    page_name: figma.currentPage.name,
    selection,
    top_level_nodes: children,
    node_count: figma.currentPage.findAll().length
  };
}

function focus(node) {
  figma.currentPage.selection = [node];
  figma.viewport.scrollAndZoomIntoView([node]);
}

async function createLandingPage(args) {
  await ensureFonts();
  const root = figma.createFrame();
  root.name = args.name || "JARVIS Landing Page";
  root.resize(1440, 3000);
  root.fills = solid(args.background_hex || "#F7F3EE");

  const accent = args.accent_hex || "#111111";
  const dark = "#111111";
  const muted = "#5B5B5B";

  const brand = await makeText(args.product_name || "Produto", 96, 62, 30, "bold", dark, "Brand");
  root.appendChild(brand);
  const nav = await makeText("PRODUTO     BENEFÍCIOS     SOBRE", 930, 68, 15, "regular", muted, "Navigation");
  root.appendChild(nav);

  const eyebrow = await makeText("NOVO · CUIDADO DIÁRIO", 96, 290, 16, "bold", accent, "Eyebrow");
  root.appendChild(eyebrow);
  const headline = await makeText(args.headline, 96, 342, 76, "bold", dark, "Hero Headline");
  headline.resize(660, headline.height);
  headline.textAutoResize = "HEIGHT";
  root.appendChild(headline);
  const sub = await makeText(args.subheadline, 96, 560, 24, "regular", muted, "Hero Subheadline");
  sub.resize(600, sub.height);
  sub.textAutoResize = "HEIGHT";
  root.appendChild(sub);

  const productCard = figma.createRectangle();
  productCard.name = "Product Visual Placeholder";
  productCard.x = 840; productCard.y = 250; productCard.resize(480, 620);
  productCard.cornerRadius = 32;
  productCard.fills = solid("#FFFFFF");
  root.appendChild(productCard);
  const productLabel = await makeText(args.product_name || "Produto", 970, 515, 34, "bold", dark, "Product Label");
  root.appendChild(productLabel);

  const cta = figma.createRectangle();
  cta.name = "Primary CTA"; cta.x = 96; cta.y = 720; cta.resize(260, 68); cta.cornerRadius = 34; cta.fills = solid(accent);
  root.appendChild(cta);
  const ctaText = await makeText(args.cta, 140, 741, 18, "bold", "#FFFFFF", "Primary CTA Label");
  root.appendChild(ctaText);

  const sectionBg = figma.createRectangle();
  sectionBg.name = "Benefits Background"; sectionBg.x = 0; sectionBg.y = 980; sectionBg.resize(1440, 850); sectionBg.fills = solid("#FFFFFF");
  root.appendChild(sectionBg);
  const sectionTitle = await makeText("Por que escolher " + (args.product_name || "este produto") + "?", 96, 1080, 46, "bold", dark, "Benefits Heading");
  root.appendChild(sectionTitle);

  const sections = Array.isArray(args.sections) && args.sections.length ? args.sections.slice(0, 4) : ["Benefício 1", "Benefício 2", "Benefício 3", "Benefício 4"];
  for (let i = 0; i < sections.length; i++) {
    const x = 96 + (i % 2) * 620;
    const y = 1220 + Math.floor(i / 2) * 250;
    const card = figma.createRectangle();
    card.name = "Benefit Card " + (i + 1); card.x = x; card.y = y; card.resize(540, 190); card.cornerRadius = 24; card.fills = solid(args.background_hex || "#F7F3EE");
    root.appendChild(card);
    const num = await makeText("0" + (i + 1), x + 28, y + 28, 16, "bold", accent, "Benefit Number " + (i + 1)); root.appendChild(num);
    const label = await makeText(sections[i], x + 28, y + 74, 26, "bold", dark, "Benefit " + (i + 1)); root.appendChild(label);
  }

  const proof = await makeText("Feito para entrar na sua rotina — sem complicar.", 180, 2040, 52, "bold", dark, "Proof Heading");
  proof.resize(1080, proof.height); proof.textAutoResize = "HEIGHT"; root.appendChild(proof);
  const proofSub = await makeText("Espaço reservado para prova social, diferenciais do produto e argumentos de compra.", 250, 2190, 22, "regular", muted, "Proof Copy");
  root.appendChild(proofSub);

  const finalBg = figma.createRectangle();
  finalBg.name = "Final CTA Background"; finalBg.x = 96; finalBg.y = 2440; finalBg.resize(1248, 380); finalBg.cornerRadius = 36; finalBg.fills = solid(accent); root.appendChild(finalBg);
  const finalTitle = await makeText(args.headline, 165, 2525, 46, "bold", "#FFFFFF", "Final CTA Heading"); finalTitle.resize(900, finalTitle.height); finalTitle.textAutoResize = "HEIGHT"; root.appendChild(finalTitle);
  const finalCta = await makeText(args.cta, 165, 2685, 20, "bold", "#FFFFFF", "Final CTA Label"); root.appendChild(finalCta);

  focus(root);
  return { id: root.id, name: root.name, width: root.width, height: root.height };
}

async function execute(plan) {
  const action = String(plan.action || "");
  const args = plan.arguments || {};
  if (!ACTIONS.includes(action)) throw new Error("Ação não permitida: " + action);

  if (action === "inspect_document") return getState();
  if (action === "undo") { figma.triggerUndo(); return { undone: true }; }
  if (action === "create_rectangle") {
    const n = figma.createRectangle(); n.name = args.name || "Rectangle"; n.x = args.x; n.y = args.y; n.resize(args.width, args.height); n.fills = solid(args.fill_hex || "#111111"); n.cornerRadius = args.corner_radius || 0; focus(n); return nodeSnapshot(n);
  }
  if (action === "create_frame") {
    const n = figma.createFrame(); n.name = args.name; n.x = args.x; n.y = args.y; n.resize(args.width, args.height); n.fills = solid(args.fill_hex || "#FFFFFF"); focus(n); return nodeSnapshot(n);
  }
  if (action === "create_text") {
    const n = await makeText(args.text, args.x, args.y, args.font_size || 32, args.font_weight || "regular", args.fill_hex || "#111111", args.name); focus(n); return nodeSnapshot(n);
  }
  if (action === "create_landing_page") return await createLandingPage(args);

  const node = await findNode(args);
  if (!node) throw new Error("Não encontrei o node solicitado no arquivo atual.");
  if (action === "set_text") {
    if (node.type !== "TEXT") throw new Error("O node alvo não é texto.");
    await ensureFonts(); node.fontName = { family: "Inter", style: "Regular" }; node.characters = args.text; focus(node); return nodeSnapshot(node);
  }
  if (action === "set_geometry") {
    if (!("x" in node) || !("resize" in node)) throw new Error("O node não aceita geometria.");
    if (args.x !== undefined) node.x = args.x; if (args.y !== undefined) node.y = args.y;
    const w = args.width !== undefined ? args.width : node.width; const h = args.height !== undefined ? args.height : node.height; node.resize(w, h); focus(node); return nodeSnapshot(node);
  }
  if (action === "set_fill") {
    if (!("fills" in node)) throw new Error("O node não aceita preenchimento."); node.fills = solid(args.fill_hex); focus(node); return nodeSnapshot(node);
  }
  if (action === "delete_node") { const id = node.id; node.remove(); return { deleted: true, id }; }
  throw new Error("Ação não implementada.");
}

figma.ui.onmessage = async (msg) => {
  if (!msg || !msg.type) return;
  if (msg.type === "load_config") {
    const cfg = (await figma.clientStorage.getAsync("jarvis_bridge")) || {};
    let clientId = cfg.client_id;
    if (!clientId) {
      clientId = "figma-" + Date.now() + "-" + Math.random().toString(16).slice(2);
      cfg.client_id = clientId;
      await figma.clientStorage.setAsync("jarvis_bridge", cfg);
    }
    figma.ui.postMessage({ type: "config", config: cfg });
  } else if (msg.type === "save_config") {
    const previous = (await figma.clientStorage.getAsync("jarvis_bridge")) || {};
    const next = { ...previous, ...msg.config };
    await figma.clientStorage.setAsync("jarvis_bridge", next);
    figma.ui.postMessage({ type: "config", config: next });
  } else if (msg.type === "request_state") {
    figma.ui.postMessage({ type: "state", state: getState(), active_document: figma.root.name });
  } else if (msg.type === "execute") {
    try {
      const result = await execute(msg.plan || {});
      figma.ui.postMessage({ type: "result", command_id: msg.command_id, ok: true, result, state: getState(), active_document: figma.root.name });
    } catch (error) {
      figma.ui.postMessage({ type: "result", command_id: msg.command_id, ok: false, error: String(error && error.message ? error.message : error), state: getState(), active_document: figma.root.name });
    }
  }
};

figma.ui.postMessage({ type: "ready" });
