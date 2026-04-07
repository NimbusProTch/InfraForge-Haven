/**
 * Official brand SVG icons for managed service types.
 * Based on official logos from each project's brand guidelines.
 */

interface IconProps {
  className?: string;
  size?: number;
}

export function PostgresIcon({ className = "", size = 20 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" className={className}>
      <defs>
        <linearGradient id="pg-a" x1="18" y1="2" x2="18" y2="34" gradientUnits="userSpaceOnUse">
          <stop stopColor="#3E6E93" />
          <stop offset="1" stopColor="#2C5A7B" />
        </linearGradient>
      </defs>
      <path
        d="M25.56 3.55c-1.17-.67-2.78-.97-4.56-.84-.62-.36-1.33-.6-2.13-.7-1.14-.14-2.25.06-3.28.5C14.75 2.1 13.9 1.9 13 1.9c-2.14 0-4.24.95-5.67 2.72C5.52 7 4.57 10.4 4.57 14.22c0 3.03.6 6.35 1.76 9.13.72 1.72 1.72 3.38 3.05 4.13.64.36 1.34.47 2.03.28.5-.14.93-.44 1.29-.85.5.62 1.14 1 1.84 1.15.76.16 1.56.03 2.3-.32.08 1.32.3 2.3.76 3.08.56.95 1.42 1.5 2.6 1.58h.17c1.01 0 2.09-.5 3.02-1.54.82-.91 1.5-2.15 1.91-3.56l.13-.45c.42.02.84-.05 1.24-.22 1.3-.55 2.08-1.84 2.45-3.47.2-.87.28-1.82.28-2.82 0-.48-.02-.97-.06-1.48.82-.39 1.43-.97 1.84-1.72.75-1.38.85-3.12.58-4.87-.29-1.87-.97-3.84-1.57-5.15-1.05-2.27-2.28-3.85-3.63-4.58z"
        fill="url(#pg-a)"
      />
      <path
        d="M23.64 6.3c.7 0 1.36.14 1.93.43 1.05.52 2.08 1.85 2.96 3.75.55 1.19 1.19 3.04 1.45 4.73.22 1.43.15 2.84-.42 3.89-.28.52-.67.92-1.17 1.2l-.38.2.06.43c.06.55.09 1.1.09 1.62 0 .93-.07 1.8-.25 2.55-.31 1.3-.9 2.24-1.85 2.64-.32.14-.67.2-1.04.18l-.64-.03-.16.62c-.1.37-.2.74-.33 1.1-.36 1.13-.93 2.14-1.58 2.87-.72.8-1.5 1.14-2.2 1.1-.81-.05-1.35-.4-1.73-1.04-.42-.72-.63-1.79-.63-3.34v-.92l-.5.07c-.56.07-1.08.05-1.54-.1-.52-.16-.96-.48-1.32-.95l-.3-.39-.34.35c-.3.31-.63.53-.98.63-.39.11-.78.06-1.17-.14-.96-.55-1.82-1.95-2.47-3.52-1.1-2.65-1.67-5.8-1.67-8.68 0-3.53.87-6.67 2.5-8.74C11.2 4.87 12.92 4.08 14 4.08c.6 0 1.16.08 1.67.24l.66.2.48-.5c.84-.87 1.76-1.37 2.8-1.5.64-.08 1.29 0 1.92.22l.58.2.5-.37c1.07-.8 2.26-1.16 3.37-1.16h-.03l.68.09z"
        fill="#336791"
      />
      <path d="M14.5 12a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0z" fill="white" />
      <circle cx="12.5" cy="11.5" r="1" fill="#336791" />
      <path d="M23 12a2 2 0 11-4 0 2 2 0 014 0z" fill="white" />
      <circle cx="21.2" cy="11.5" r=".9" fill="#336791" />
      <path
        d="M15 17.5c0 .5.3 1 .8 1.3.5.3 1.2.5 2 .5s1.5-.2 2-.5c.5-.3.8-.8.8-1.3"
        fill="none"
        stroke="white"
        strokeWidth=".8"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function RedisIcon({ className = "", size = 20 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" className={className}>
      <path
        d="M34.16 21.18c-2.22 1.16-13.7 5.87-16.15 7.14-2.45 1.28-3.81 1.26-5.74.36C10.32 27.79 1.36 23.32 1.36 23.32v3.41s8.94 4.6 10.92 5.5c1.93.9 3.29.92 5.74-.36 2.45-1.27 13.72-5.82 15.94-6.97.74-.38 1.1-.75 1.1-1.1v-3.28c0 .35-.16.67-.9 1.06"
        fill="#912626"
      />
      <path
        d="M34.16 17.87c-2.22 1.16-13.7 5.87-16.15 7.14-2.45 1.28-3.81 1.26-5.74.36C10.32 24.48 1.36 20 1.36 20v3.41s8.94 4.6 10.92 5.5c1.93.9 3.29.92 5.74-.36 2.45-1.27 13.72-5.82 15.94-6.97.74-.38 1.1-.75 1.1-1.1v-3.28c0 .35-.16.67-.9 1.06"
        fill="#C6302B"
      />
      <path
        d="M34.16 14.16c-2.22 1.16-13.7 5.87-16.15 7.15-2.45 1.27-3.81 1.25-5.74.35C10.32 20.77 1.36 16.3 1.36 16.3v3.41s8.94 4.6 10.92 5.5c1.93.9 3.29.92 5.74-.36 2.45-1.27 13.72-5.82 15.94-6.97.74-.38 1.1-.75 1.1-1.1v-3.28c0 .35-.16.67-.9 1.06"
        fill="#912626"
      />
      <path
        d="M34.16 10.85c-2.22 1.16-13.7 5.87-16.15 7.14-2.45 1.28-3.81 1.26-5.74.36C10.32 17.46 1.36 13 1.36 13s8.94-3.85 11.13-4.82c2.19-1 3.64-.99 5.63-.12 2 .86 13.82 3.97 16.04 5.12.74.39 1.1.75 1.1 1.1 0 .35-.16.67-.9 1.06"
        fill="#C6302B"
      />
      <path d="M24.1 9.6l-6.24 2.57-5.48-2.27 6.25-2.57L24.1 9.6z" fill="#FFF" />
      <path d="M14.26 12.47l-3.02-4.74 9.52-3.86 1.03 4.34-7.53 4.26z" fill="#621B1C" />
      <ellipse cx="11.32" cy="8.47" rx="4.36" ry="1.72" fill="#FFF" />
    </svg>
  );
}

export function MongoDBIcon({ className = "", size = 20 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" className={className}>
      <path
        d="M18.96 1.86c-.5-.63-.84-1.26-.92-1.54a.2.2 0 00-.2 0c-.08.27-.42.91-.92 1.54C11.86 8.76 4.55 13.2 4.55 23.79c0 6.82 4.99 12.47 11.59 13.72.23.04.47-.13.47-.37v-2.82a.47.47 0 00-.23-.4c-3.16-1.81-5.3-5.23-5.3-9.17 0-5.86 4.25-10.91 7.06-13.64a.36.36 0 01.5 0c2.81 2.73 7.07 7.78 7.07 13.64 0 3.94-2.14 7.36-5.3 9.17a.47.47 0 00-.23.4v2.82c0 .24.24.41.47.37 6.6-1.25 11.59-6.9 11.59-13.72 0-10.59-7.72-15.03-12.28-21.93z"
        fill="#00684A"
      />
      <path
        d="M18 31.9c-.59 0-1.07-.08-1.07-.19v-4.85c0-.1.48-.19 1.07-.19s1.07.09 1.07.19v4.85c0 .11-.48.19-1.07.19z"
        fill="#B8C4C2"
      />
    </svg>
  );
}

export function MySQLIcon({ className = "", size = 20 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" className={className}>
      <path
        d="M32.7 27.3c-1.6-.6-2.8-.9-3.9-.9-.1 0-.3 0-.4.1h-.1c-.3.1-.6.4-.9.8-.1.1-.2.2-.2.3-.5-.3-1-.6-1.6-.8-1.2-.5-2.6-.7-3.9-.7-1.8 0-3.2.5-4.3 1.1-.2-.1-.4-.2-.7-.3-1-.3-1.9-.3-3 0-.5.2-1 .5-1.5.9-.2-.2-.5-.5-.8-.6-.8-.4-1.6-.4-2.5-.2-.8.2-1.6.7-2.4 1.5l-.5.5.7.4c.9.5 1.7.9 2.5 1.2 1.5.5 2.9.5 4-.1.3-.2.6-.4.8-.7.2.1.5.2.7.2.8.2 1.6.1 2.5-.2.4-.1.7-.3 1.1-.5.5.4 1.2.7 2 .9 1.5.3 3.3.1 4.9-.7.3-.2.6-.3.8-.5.5.2 1.1.4 1.7.4 1.2.1 2.5-.2 3.8-.8l.7-.3-.6-.4-.3-.2z"
        fill="#00758F"
      />
      <path
        d="M18.6 5.2c-5.2 0-9.4 1.2-9.4 2.6v20.4c0 1.4 4.2 2.6 9.4 2.6s9.4-1.2 9.4-2.6V7.8c0-1.4-4.2-2.6-9.4-2.6z"
        fill="#F29111"
        opacity=".3"
      />
      <ellipse cx="18.6" cy="7.8" rx="9.4" ry="2.6" fill="#F29111" />
      <path
        d="M18.6 5.2c-5.2 0-9.4 1.2-9.4 2.6s4.2 2.6 9.4 2.6 9.4-1.2 9.4-2.6-4.2-2.6-9.4-2.6zm0 4c-4.2 0-7.6-.8-7.6-1.8s3.4-1.8 7.6-1.8 7.6.8 7.6 1.8-3.4 1.8-7.6 1.8z"
        fill="#00758F"
      />
      <text x="8" y="23" fill="#00758F" fontFamily="Arial,sans-serif" fontWeight="bold" fontSize="10">My</text>
      <text x="18.5" y="23" fill="#F29111" fontFamily="Arial,sans-serif" fontWeight="bold" fontSize="10">SQL</text>
    </svg>
  );
}

export function RabbitMQIcon({ className = "", size = 20 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" className={className}>
      <path
        d="M31.13 13.38h-8.06a1 1 0 01-1-1V4.88a1 1 0 00-1-1h-4.64a1 1 0 00-1 1v7.5a1 1 0 01-1 1H11.8a1 1 0 01-1-1V4.88a1 1 0 00-1-1H5.17a1 1 0 00-1 1v26.25a1 1 0 001 1h25.96a1 1 0 001-1V14.38a1 1 0 00-1-1z"
        fill="#FF6600"
      />
      <rect x="10.5" y="17.38" width="5" height="5" rx="1" fill="white" opacity=".9" />
      <rect x="17.5" y="17.38" width="5" height="5" rx="1" fill="white" opacity=".9" />
      <rect x="24.5" y="17.38" width="5" height="5" rx="1" fill="white" opacity=".9" />
      <rect x="10.5" y="24.38" width="5" height="5" rx="1" fill="white" opacity=".9" />
      <rect x="17.5" y="24.38" width="5" height="5" rx="1" fill="white" opacity=".9" />
      <rect x="24.5" y="24.38" width="5" height="5" rx="1" fill="white" opacity=".9" />
    </svg>
  );
}

/** Get the appropriate icon component for a service type */
export function ServiceIcon({ type, className = "", size = 20 }: { type: string } & IconProps) {
  switch (type) {
    case "postgres":
      return <PostgresIcon className={className} size={size} />;
    case "redis":
      return <RedisIcon className={className} size={size} />;
    case "mongodb":
      return <MongoDBIcon className={className} size={size} />;
    case "mysql":
      return <MySQLIcon className={className} size={size} />;
    case "rabbitmq":
      return <RabbitMQIcon className={className} size={size} />;
    default:
      return <span className={`inline-block w-5 h-5 rounded bg-gray-300 dark:bg-zinc-700 ${className}`} />;
  }
}
