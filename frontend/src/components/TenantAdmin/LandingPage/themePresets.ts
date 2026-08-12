export interface ThemePreset {
  id: string;
  name: string;
  color_primary: string;
  color_accent: string;
  section_bg: string;
  font_heading: string;
  font_body: string;
}

export const THEME_PRESETS: ThemePreset[] = [
  {
    id: "professional",
    name: "Professional",
    color_primary: "#2D5F8A",
    color_accent: "#F4A261",
    section_bg: "#ffffff",
    font_heading: "Inter",
    font_body: "Inter",
  },
  {
    id: "warm",
    name: "Warm",
    color_primary: "#8B4513",
    color_accent: "#DAA520",
    section_bg: "#FFF8F0",
    font_heading: "Lora",
    font_body: "Nunito",
  },
  {
    id: "modern",
    name: "Modern",
    color_primary: "#1a1a2e",
    color_accent: "#e94560",
    section_bg: "#16213e",
    font_heading: "Poppins",
    font_body: "Poppins",
  },
  {
    id: "nature",
    name: "Nature",
    color_primary: "#2d6a4f",
    color_accent: "#95d5b2",
    section_bg: "#f0f7f4",
    font_heading: "Nunito",
    font_body: "Nunito",
  },
  {
    id: "minimal",
    name: "Minimal",
    color_primary: "#333333",
    color_accent: "#666666",
    section_bg: "#ffffff",
    font_heading: "system",
    font_body: "system",
  },
  {
    id: "luxury",
    name: "Luxury",
    color_primary: "#1c1c1c",
    color_accent: "#c9a96e",
    section_bg: "#0d0d0d",
    font_heading: "Playfair Display",
    font_body: "Lato",
  },
];
