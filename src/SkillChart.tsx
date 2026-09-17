import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type ChartSkill = {
  shortName: string;
  percentage: number;
};

export default function SkillChart({ data }: { data: ChartSkill[] }) {
  const [isMobile, setIsMobile] = useState(() =>
    window.matchMedia("(max-width: 620px)").matches,
  );

  useEffect(() => {
    const media = window.matchMedia("(max-width: 620px)");
    const updateLayout = () => setIsMobile(media.matches);
    media.addEventListener("change", updateLayout);
    return () => media.removeEventListener("change", updateLayout);
  }, []);

  if (!isMobile) {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 8, right: 50, left: 8, bottom: 8 }}
        >
          <CartesianGrid horizontal={false} stroke="#e5e9ef" />
          <XAxis
            type="number"
            domain={[0, 100]}
            tickFormatter={(value) => `${value}%`}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="shortName"
            width={220}
            interval={0}
            axisLine={false}
            tickLine={false}
            tickMargin={10}
            tick={{
              fill: "#253142",
              fontSize: 12,
              fontWeight: 650,
            }}
          />
          <Tooltip content={() => null} cursor={{ fill: "#f3f6f9" }} />
          <Bar
            dataKey="percentage"
            fill="#2474c5"
            activeBar={{ fill: "#1e64ab" }}
            radius={[0, 5, 5, 0]}
            barSize={20}
          >
            <LabelList
              dataKey="percentage"
              position="right"
              formatter={(value) => `${value}%`}
              fill="#506074"
              fontSize={12}
              fontWeight={700}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  return (
    <div className="mobile-skill-chart">
      {data.map((skill) => {
        const percentage = Math.min(Math.max(skill.percentage, 0), 100);
        return (
          <div className="mobile-skill-row" key={skill.shortName}>
            <span className="mobile-skill-name">{skill.shortName}</span>
            <div className="mobile-skill-bar">
              <span
                className="mobile-skill-fill"
                style={{ width: `${percentage}%` }}
              />
              <strong
                className="mobile-skill-value"
                style={{ left: `${percentage}%` }}
              >
                {skill.percentage}%
              </strong>
            </div>
          </div>
        );
      })}
      <div className="mobile-skill-axis">
        <span />
        <div>
          <span>0%</span>
          <span>25%</span>
          <span>50%</span>
          <span>75%</span>
          <span>100%</span>
        </div>
      </div>
    </div>
  );
}
