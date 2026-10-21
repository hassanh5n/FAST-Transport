// The registration sequence, shown where a passenger has not registered yet.
// Numbered because it is a real order of steps.
import { colors, fonts } from "../../theme";
import { REGISTRATION_STEPS } from "./transportHelpers";

export default function RegistrationSteps({ layout = "row" }) {
  return (
    <ol className={`reg-steps reg-steps--${layout}`}>
      {REGISTRATION_STEPS.map(({ title, text }, i) => (
        <li key={title} className="reg-steps__item">
          <span className="reg-steps__num" aria-hidden="true">{i + 1}</span>
          <div>
            <div style={{ fontFamily: fonts.heading, fontWeight: 700, fontSize: 14, color: colors.textPrimary }}>{title}</div>
            <p style={{ margin: "3px 0 0", fontSize: 13, lineHeight: 1.55, color: colors.textSecondary }}>{text}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
