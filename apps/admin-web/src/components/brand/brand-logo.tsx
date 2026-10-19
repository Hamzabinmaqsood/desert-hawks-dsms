import { PRODUCT_NAME, PRODUCT_SHORT_NAME } from "@/lib/product";

export function BrandLogo({
  className = "",
}: {
  className?: string;
  priority?: boolean;
}) {
  return (
    <span
      aria-label={`${PRODUCT_NAME} mark`}
      className={`brand-logo ${className}`.trim()}
      role="img"
    >
      {PRODUCT_SHORT_NAME}
    </span>
  );
}
