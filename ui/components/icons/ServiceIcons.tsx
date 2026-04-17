/**
 * Service icons using official brand SVGs from /public/icons/.
 */
import Image from "next/image";

interface IconProps {
  className?: string;
  size?: number;
}

const ICON_MAP: Record<string, { src: string; alt: string }> = {
  postgres: { src: "/icons/postgresql.svg", alt: "PostgreSQL" },
  mysql: { src: "/icons/mysql.svg", alt: "MySQL" },
  mongodb: { src: "/icons/mongodb.svg", alt: "MongoDB" },
  redis: { src: "/icons/redis.svg", alt: "Redis" },
  rabbitmq: { src: "/icons/rabbitmq.svg", alt: "RabbitMQ" },
  kafka: { src: "/icons/kafka.svg", alt: "Apache Kafka" },
};

export function ServiceIcon({ type, className = "", size = 20 }: { type: string } & IconProps) {
  const icon = ICON_MAP[type];
  if (!icon) {
    return <span className={`inline-block rounded bg-gray-300 dark:bg-zinc-700 ${className}`} style={{ width: size, height: size }} />;
  }
  return (
    <Image
      src={icon.src}
      alt={icon.alt}
      width={size}
      height={size}
      className={className}
      unoptimized
    />
  );
}

// Named exports for backward compatibility
export function PostgresIcon(props: IconProps) {
  return <ServiceIcon type="postgres" {...props} />;
}
export function RedisIcon(props: IconProps) {
  return <ServiceIcon type="redis" {...props} />;
}
export function MongoDBIcon(props: IconProps) {
  return <ServiceIcon type="mongodb" {...props} />;
}
export function MySQLIcon(props: IconProps) {
  return <ServiceIcon type="mysql" {...props} />;
}
export function RabbitMQIcon(props: IconProps) {
  return <ServiceIcon type="rabbitmq" {...props} />;
}
export function KafkaIcon(props: IconProps) {
  return <ServiceIcon type="kafka" {...props} />;
}
