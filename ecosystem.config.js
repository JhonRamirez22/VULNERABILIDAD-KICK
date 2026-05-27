module.exports = {
  apps: [
    {
      name: 'token-server',
      script: './token_server.py',
      interpreter: 'python3',
      env: {
        NODE_ENV: 'production',
      },
      restart_delay: 4000,
      max_memory_restart: '1G',
      error_file: './logs/token-server-error.log',
      out_file: './logs/token-server-out.log',
    },
    {
      name: 'proxy-checker',
      script: './proxy_checker.py',
      interpreter: 'python3',
      env: {
        NODE_ENV: 'production',
      },
      restart_delay: 4000,
      max_memory_restart: '500M',
      error_file: './logs/proxy-checker-error.log',
      out_file: './logs/proxy-checker-out.log',
    },
    {
      name: 'proxy-rotator',
      script: './proxy_rotator.py',
      args: '--socks5-port 1080 --upstream-file upstreams.txt',
      interpreter: 'python3',
      env: {
        NODE_ENV: 'production',
      },
      restart_delay: 4000,
      max_memory_restart: '2G',
      error_file: './logs/proxy-rotator-error.log',
      out_file: './logs/proxy-rotator-out.log',
    },
    {
      name: 'kick-bot-cluster',
      script: './kick-websocket.js',
      instances: 4,  // 4 instancias paralelas
      exec_mode: 'cluster',
      args: 'https://kick.com/tanizen 5000',
      env: {
        NODE_ENV: 'production',
      },
      max_memory_restart: '2G',
      error_file: './logs/kick-bot-error.log',
      out_file: './logs/kick-bot-out.log',
    },
  ],
};
