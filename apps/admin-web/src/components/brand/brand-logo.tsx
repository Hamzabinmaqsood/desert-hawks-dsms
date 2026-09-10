import Image from "next/image";

export function BrandLogo({
  className = "",
  priority = false,
}: {
  className?: string;
  priority?: boolean;
}) {
  return (
    <Image
      className={`brand-logo ${className}`.trim()}
      src="/brand/desert-hawks-logo.png"
      alt="Desert Hawks official logo"
      width={1028}
      height={1070}
      priority={priority}
    />
  );
}
