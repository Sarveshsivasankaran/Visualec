import fs from "node:fs/promises";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const input = "../PPT'S/Visualec_MAST_ESP32S3_Architecture.pptx";
const out = "source-inspect";
await fs.mkdir(out, { recursive: true });
const deck = await PresentationFile.importPptx(await FileBlob.load(input));
const snapshot = await deck.inspect({
  kind: "slide,textbox,shape,image,table,chart,notes,layout",
  include: "id,slide,name,title,text,textPreview,bbox,isPlaceholder,placeholders",
  maxChars: 120000,
});
await fs.writeFile(`${out}/template-inspect.ndjson`, snapshot.ndjson);
for (let index = 0; index < deck.slides.items.length; index += 1) {
  const slide = deck.slides.getItem(index);
  const png = await deck.export({ slide, format: "png", scale: 1 });
  await fs.writeFile(`${out}/slide-${String(index + 1).padStart(2, "0")}.png`, new Uint8Array(await png.arrayBuffer()));
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(`${out}/slide-${String(index + 1).padStart(2, "0")}.layout.json`, await layout.text());
}
const montage = await deck.export({ format: "webp", montage: true, scale: 1 });
await fs.writeFile(`${out}/montage.webp`, new Uint8Array(await montage.arrayBuffer()));
console.log(`inspected ${deck.slides.items.length} slides`);
