'use client';
import { CircularProgressbar, buildStyles } from 'react-circular-progressbar';
import 'react-circular-progressbar/dist/styles.css';

export default function ATSScore({ score }: { score: number }) {
  return (
    <div className="w-40 h-40 mx-auto">
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
  );
}