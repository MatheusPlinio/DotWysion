from dotenv import load_dotenv
import os
from typing import cast

# Carrega as variáveis do arquivo .env
load_dotenv()

def get_env_var(var_name: str) -> str:
    value = os.getenv(var_name)
    if value is None:
        raise ValueError(f"Variável de ambiente {var_name} não encontrada")
    return value

# Configurações do Discord
DISCORD_TOKEN = get_env_var('DISCORD_TOKEN')
DISCORD_GUILD = get_env_var('DISCORD_GUILD')

# Configurações do Supabase
SUPABASE_URL = get_env_var('SUPABASE_URL')
SUPABASE_KEY = get_env_var('SUPABASE_KEY')

# Outras configurações que podem ter valores padrão
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')
