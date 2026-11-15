// Fonts the author still chooses from in T1.1 (decision 130), shown on the dev
// page ?mode=dev&tool=tmt (dev-tmt.js). Sizes and layouts are decided
// (decisions 127, 128). When the font is chosen, it moves to PARAMS.tmt and
// this file goes away.

export const FONT_IDS = ['montserrat', 'montserrat600', 'arsenal', 'lineseed'];

export const DEFAULT_CHOICE = {
  part: 'b',
  font: 'montserrat',
  show: { path: false, border: true, cross: false },
};

// What to look at when choosing the font, in two lines per font: the pairs
// named in decision 121, then other look-alikes and the widest labels.
export const SPECIMEN = [
  [['З', '3', '13'], ['Г', 'Ґ'], ['Е', 'Є'], ['И', 'І']],
  [['І', '1'], ['В', '8'], ['Б', '6'], ['10', '12', '25']],
];
