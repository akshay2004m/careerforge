'use client';
import { CircularProgressbar, buildStyles } from 'react-circular-progressbar';
import 'react-circular-progressbar/dist/styles.css';

export default function ATSScore({ score, size, label }: { score: number; size?: number; label?: string }) {
  return (
    <div className="flex flex-col items-center mx-auto" style={size ? { width: size, height: size } : {}}>
      <div className={!size ? "w-40 h-40" : "w-full h-full"}>
        <CircularProgressbar
          value={score}
          text={`${score}%`}
          styles={buildStyles({
            pathColor: score > 80 ? "#22c55e" : "#eab308",
            textColor: "#fff",
            trailColor: "#27272a",
            textSize: "18px",
          })}
        />
      </div>
      {label && <div className="mt-2 text-sm text-zinc-400">{label}</div>}
    </div>
  );
}
