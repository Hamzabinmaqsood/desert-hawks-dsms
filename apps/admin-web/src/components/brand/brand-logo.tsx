export function BrandLogo({
  className = "",
}: {
  className?: string;
  priority?: boolean;
}) {
  return (
    <span
      aria-label="DSMS platform mark"
      className={`brand-logo ${className}`.trim()}
      role="img"
    >
      DSMS
    </span>
  );
}
