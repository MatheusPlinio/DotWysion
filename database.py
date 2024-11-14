from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# SQL para verificar se a tabela existe
def tabela_existe(tabela_nome: str) -> bool:
    query = f"""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = '{tabela_nome}'
        );
    """
    resposta = supabase.rpc('sql', {'sql': query}).execute()
    return resposta.data[0]['exists']

# SQL para criar a tabela, se ela não existir
def criar_tabela_registros():
    sql_create_table = """
    CREATE TYPE tipo_ponto AS ENUM (
        'entrada',
        'saida',
        'pausa_inicio',
        'pausa_fim'
    );

    CREATE TABLE registros (
        id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
        user_id TEXT NOT NULL,
        user_name VARCHAR(255) NOT NULL, -- Usando VARCHAR para 'user_name' com limite de 255 caracteres
        tipo tipo_ponto NOT NULL, -- Usando o tipo ENUM para 'tipo'
        data_hora TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::TEXT, now()),
        observacao TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::TEXT, now())
    );
    """
    supabase.rpc('sql', {'sql': sql_create_table}).execute()

# Verifica se a tabela 'registros' existe, e a cria caso não exista
if not tabela_existe('registros'):
    criar_tabela_registros()
    print("Tabela 'registros' criada.")
else:
    print("Tabela 'registros' já existe.")
