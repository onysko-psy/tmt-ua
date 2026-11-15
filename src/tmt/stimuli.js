// Fixed parts of the TMT stimuli: where the layout and the fonts are, and
// drawing details that are not research parameters. Sizes in mm are in
// PARAMS.tmt (config.js).

export const LAYOUT_URL = 'stimuli/tmt-layout.json'; // decision 128
export const FONTS_URL = 'src/fonts/fonts.json';
export const FONTS_DIR = 'src/fonts/';

export const STYLE = {
  circleStrokeMm: 0.4,
  lineMm: 0.5,
  crossMm: 8,
};

export const PARTS = [
  { id: 'a', label: 'A' },
  { id: 'b', label: 'B' },
  { id: 'practice_a', label: 'Пробна A' },
  { id: 'practice_b', label: 'Пробна B' },
];

// Loads the bundled fonts with these ids (all when ids is null); resolves to
// their entries from fonts.json once the browser can draw them.
export async function loadFonts(ids = null) {
  const { fonts } = await (await fetch(FONTS_URL)).json();
  const wanted = ids ? ids.map((id) => fonts.find((font) => font.id === id)) : fonts;
  await Promise.all(
    wanted.map(async (font) => {
      const face = new FontFace(font.family, `url(${FONTS_DIR}${font.file})`, { weight: String(font.weight) });
      document.fonts.add(await face.load());
    }),
  );
  return wanted;
}
