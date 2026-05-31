# RMM (Remote Monitoring and Management)

Полнофункциональная система для удаленного мониторинга и управления компьютерами в локальной сети или через интернет. Состоит из серверной части на Python/Flask и кроссплатформенного агента на Rust.

## 🎯 Возможности

- **Управление агентами** — регистрация, мониторинг статуса и удаление устройств
- **Исполнение команд** — выполнение shell/PowerShell команд на удалённых машинах в реальном времени
- **Передача файлов** — загрузка и скачивание файлов с/на удалённые машины
- **Мониторинг системы** — сбор информации о ОС, процессах и сервисах
- **WebSocket Real-Time** — двусторонняя связь для мгновенных обновлений
- **Панель администратора** — веб-интерфейс для управления и просмотра логов
- **Аудит операций** — логирование всех действий администраторов
- **JWT аутентификация** — защищенный доступ к API
- **TLS/SSL** — автоматическая генерация сертификатов с поддержкой SAN для локальной сети

## 📋 Требования

### Для запуска серверной части

- Docker и Docker Compose
- (или) Python 3.11+, PostgreSQL 16, pip

### Для сборки агента

- Rust 1.70+
- Cargo

### Для использования

- Браузер с поддержкой WebSocket (Chrome, Firefox, Safari, Edge)
- Сетевое соединение до сервера (локальная сеть или интернет)

## 🚀 Быстрый старт

### 1. С Docker (рекомендуется)

```bash
# Клонируйте репозиторий
git clone https://github.com/Ch3z2z/Remote-PC-managment.git
cd Remote-PC-managment

# Скопируйте пример конфигурации
cp .env.example .env

# Запустите контейнеры
docker compose up --build
```

Сервер будет доступен по адресу:
- `https://localhost:8443` (локально)
- `https://<YOUR_IP>:8443` (из локальной сети)

### 2. Без Docker (локальная разработка)

#### Сервер

```bash
cd server

# Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# Установите зависимости
pip install -r requirements.txt

# Запустите миграции БД (при первом запуске)
flask db upgrade

# Запустите сервер
python run.py
```

#### Агент

```bash
cd agent

# Отредактируйте config.json с адресом сервера
# Скомпилируйте для вашей ОС
cargo build --release

# Запустите агента
./target/release/rmm-agent  # Linux/Mac
# или
target\release\rmm-agent.exe  # Windows
```

## ⚙️ Конфигурация

### Переменные окружения (.env)

```env
# Сервер
PORT=8443
USE_TLS=true
SECRET_KEY=your-secret-key-change-me
JWT_SECRET_KEY=your-jwt-secret-change-me
ADMIN_PASSWORD=Admin_Win_123!

# База данных
POSTGRES_DB=rmm_dev
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
DATABASE_URL=postgresql://postgres:postgres@db:5432/rmm_dev

# Сеть и сертификаты
SERVER_PUBLIC_HOSTS=192.168.1.50,example.com
AGENT_SERVER_HOST=192.168.1.50:8443
CERT_FORCE_RENEW=false

# Файлы
UPLOAD_FOLDER=/app/uploads
```

### Для доступа из локальной сети на Windows

Используйте вспомогательный скрипт для автоматического обнаружения IP:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/docker-lan.ps1 -Build
```

Или установите переменные вручную:

```env
SERVER_PUBLIC_HOSTS=192.168.1.50
AGENT_SERVER_HOST=192.168.1.50:8443
```

### Конфигурация агента (agent/config.json)

```json
{
  "server_url": "https://192.168.1.50:8443",
  "ca_cert_path": "certs/ca.crt",
  "agent_cert": "certs/agent.crt",
  "agent_key": "certs/agent.key",
  "heartbeat_interval": 30,
  "log_level": "info"
}
```

## 📱 Использование

### Вход в панель администратора

1. Откройте браузер: `https://localhost:8443`
2. Введите учетные данные:
   - Пользователь: `admin`
   - Пароль: значение `ADMIN_PASSWORD` (по умолчанию `Admin_Win_123!`)

### Регистрация агента

1. На сервере скачайте пакет агента: **Admin Panel → Download Agent Package**
2. На целевой машине распакуйте и запустите агент
3. Агент автоматически регистрируется и появляется в списке

### Выполнение команд

1. В панели выберите агент
2. Перейдите на вкладку **Commands**
3. Введите команду (shell для Linux/Mac, PowerShell для Windows)
4. Результат появится в реальном времени через WebSocket

### Управление файлами

1. Выберите агент → **Files**
2. Загрузить: выберите файл и отправьте
3. Скачать: введите путь на удалённой машине

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    Web Browser                              │
│         (Admin Panel + WebSocket Client)                    │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  │ HTTPS / WebSocket
                  │
┌─────────────────▼───────────────────────────────────────────┐
│              Flask Server (Python)                           │
│  ┌──────────────┬──────────────┬──────────────────────────┐ │
│  │ REST API     │ WebSocket    │ Admin Panel              │ │
│  │ /api/v1/...  │ /ws/agent    │ /dashboard, /login, etc  │ │
│  └──────────────┴──────────────┴──────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ SQLAlchemy ORM                                         │ │
│  │ (Users, Agents, Commands, AuditLog, Files)            │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────┬───────────────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
    HTTPS/TLS           PostgreSQL
        │                   │
┌───────▼────────┐    ┌─────▼──────┐
│  RMM Agents    │    │  Database  │
│  (Rust)        │    │  (DB Data) │
└────────────────┘    └────────────┘
```

## 🔐 Безопасность

- **TLS 1.2+** — все соединения защищены
- **Самоподписанные сертификаты** — автоматически генерируются при запуске
- **JWT токены** — для аутентификации агентов и пользователей
- **Хеширование паролей** — bcrypt с солью
- **Rate limiting** — защита от перебора паролей
- **CSRF защита** — на формах административной панели
- **Аудит логирования** — отслеживание всех операций

## 🧪 Разработка

### Запуск тестов

```bash
cd server
pytest tests/ -v
```

### Структура проекта

```
.
├── agent/              # Rust агент
│  ├── src/
│  │  ├── main.rs
│  │  ├── auth.rs
│  │  ├── websocket_client.rs
│  │  ├── command_executor.rs
│  │  └── ...
│  ├── Cargo.toml
│  └── certs/           # Сертификаты для агента
│
├── server/             # Python Flask сервер
│  ├── app/
│  │  ├── __init__.py
│  │  ├── models.py
│  │  ├── views.py
│  │  ├── websocket.py
│  │  ├── cert_bootstrap.py
│  │  ├── api/          # REST API endpoints
│  │  │  ├── admin.py
│  │  │  ├── agents.py
│  │  │  ├── commands.py
│  │  │  ├── files.py
│  │  │  └── auth_routes.py
│  │  ├── static/       # CSS, JS
│  │  ├── templates/    # HTML шаблоны
│  │  └── ...
│  ├── tests/
│  ├── run.py           # Точка входа
│  ├── requirements.txt
│  ├── certs/           # Сертификаты сервера
│  └── pytest.ini
│
├── scripts/            # Вспомогательные скрипты
│  └── docker-lan.ps1   # PowerShell для Windows
│
├── docker-compose.yml  # Конфигурация контейнеров
├── Dockerfile          # Образ для сборки
└── README.md          # Этот файл
```

## 📦 API Endpoints

### Аутентификация

- `POST /api/v1/auth/login` — вход пользователя
- `POST /api/v1/auth/logout` — выход пользователя

### Агенты

- `GET /api/v1/agents/` — список агентов
- `POST /api/v1/agents/register` — регистрация агента
- `GET /api/v1/agents/<id>` — информация об агенте
- `DELETE /api/v1/agents/<id>` — удаление агента

### Команды

- `POST /api/v1/agents/<id>/commands` — выполнить команду
- `GET /api/v1/agents/<id>/commands` — история команд
- `GET /api/v1/commands/<cmd_id>` — результат команды

### Файлы

- `POST /api/v1/agents/<id>/files/upload` — загрузить файл
- `GET /api/v1/agents/<id>/files/download` — скачать файл

### WebSocket

- `WS /ws/agent` — двусторонняя связь с агентом


