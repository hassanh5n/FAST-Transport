import { input } from "../theme";

export const inputStyle = {
  ...input,
  transition: "border-color 0.15s",
};

export const selectStyle = {
  ...input,
  appearance: "none",
  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%235b7489'/%3E%3C/svg%3E")`,
  backgroundRepeat: "no-repeat",
  backgroundPosition: "right 12px center",
  paddingRight: "30px",
  cursor: "pointer",
};
