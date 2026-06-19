type Variant = "green" | "blue" | "yellow" | "red" | "gray";

const cls: Record<Variant, string> = {
  green:  "bg-green-50 text-green-700 ring-green-600/20",
  blue:   "bg-blue-50 text-blue-700 ring-blue-600/20",
  yellow: "bg-yellow-50 text-yellow-800 ring-yellow-600/20",
  red:    "bg-red-50 text-red-700 ring-red-600/20",
  gray:   "bg-gray-50 text-gray-600 ring-gray-500/20",
};

export function Badge({ children, variant = "gray" }: { children: React.ReactNode; variant?: Variant }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls[variant]}`}>
      {children}
    </span>
  );
}
