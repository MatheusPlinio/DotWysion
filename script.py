import discord
from discord.ext import commands
from discord import ui
import datetime
from supabase import create_client, Client
from config import DISCORD_TOKEN, SUPABASE_URL, SUPABASE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

"""
-- SQL para criar a tabela no Supabase:
create table registros (
    id bigint primary key generated always as identity,
    user_id text not null,
    user_name text not null,
    tipo text not null, -- 'entrada', 'saida', 'pausa_inicio', 'pausa_fim'
    data_hora timestamp with time zone default timezone('utc'::text, now()),
    observacao text,
    created_at timestamp with time zone default timezone('utc'::text, now())
);
"""

class PontoButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        self.entrada_button.disabled = False
        self.pausa_inicio_button.disabled = True
        self.pausa_fim_button.disabled = True
        self.saida_button.disabled = True
        self.relatorio_button.disabled = False

    async def update_button_states(self, user_id: str):
        """Update button states based on user's current status"""
        try:
            data = supabase.table('registros')\
                .select("*")\
                .eq('user_id', user_id)\
                .order('data_hora', desc=True)\
                .limit(1)\
                .execute()

            if not data.data:
                self.entrada_button.disabled = False
                self.pausa_inicio_button.disabled = True
                self.pausa_fim_button.disabled = True
                self.saida_button.disabled = True
                self.relatorio_button.disabled = False
                return

            ultimo_registro = data.data[0]
            tipo = ultimo_registro['tipo']

            self.entrada_button.disabled = True
            self.pausa_inicio_button.disabled = True
            self.pausa_fim_button.disabled = True
            self.saida_button.disabled = True
            self.relatorio_button.disabled = False

            if tipo == 'entrada':
                self.pausa_inicio_button.disabled = False
                self.saida_button.disabled = False
            elif tipo == 'pausa_inicio':
                self.pausa_fim_button.disabled = False
            elif tipo == 'pausa_fim':
                self.pausa_inicio_button.disabled = False
                self.saida_button.disabled = False
            elif tipo == 'saida':
                self.entrada_button.disabled = False

        except Exception as e:
            print(f"Error updating button states: {e}")

    @discord.ui.button(label="Registrar Entrada", style=discord.ButtonStyle.green, custom_id="entrada")
    async def entrada_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await registrar_entrada_interaction(interaction)
        await self.update_button_states(str(interaction.user.id))
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Iniciar Pausa", style=discord.ButtonStyle.blurple, custom_id="pausa_inicio")
    async def pausa_inicio_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await registrar_pausa_inicio_interaction(interaction)
        await self.update_button_states(str(interaction.user.id))
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Retornar da Pausa", style=discord.ButtonStyle.blurple, custom_id="pausa_fim")
    async def pausa_fim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await registrar_pausa_fim_interaction(interaction)
        await self.update_button_states(str(interaction.user.id))
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Encerrar Expediente", style=discord.ButtonStyle.red, custom_id="saida")
    async def saida_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await registrar_saida_interaction(interaction)
        await self.update_button_states(str(interaction.user.id))
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Ver Relatório", style=discord.ButtonStyle.grey, custom_id="relatorio")
    async def relatorio_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await gerar_relatorio_interaction(interaction)

async def verificar_usuario_ponto(user_id: str) -> bool:
    """Verifica se o usuário tem um ponto aberto"""
    try:
        data = supabase.table('registros')\
            .select("*")\
            .eq('user_id', user_id)\
            .order('data_hora', desc=True)\
            .limit(1)\
            .execute()

        if not data.data:
            return True

        ultimo_registro = data.data[0]
        return ultimo_registro['tipo'] in ['saida', None]
    except Exception as e:
        print(f"Erro ao verificar usuário: {e}")
        return False

async def verificar_permissao_acao(interaction: discord.Interaction, tipo_acao: str) -> bool:
    """Verifica se o usuário pode realizar a ação solicitada"""
    try:
        data = supabase.table('registros')\
            .select("*")\
            .eq('user_id', str(interaction.user.id))\
            .order('data_hora', desc=True)\
            .limit(1)\
            .execute()

        if not data.data:
            if tipo_acao != 'entrada':
                await interaction.response.send_message(
                    "❌ Você precisa registrar uma entrada primeiro!",
                    ephemeral=True
                )
                return False
            return True

        ultimo_registro = data.data[0]

        if tipo_acao == 'entrada' and ultimo_registro['tipo'] != 'saida':
            await interaction.response.send_message(
                "❌ Você já tem um ponto aberto!",
                ephemeral=True
            )
            return False

        if tipo_acao == 'pausa_inicio' and ultimo_registro['tipo'] not in ['entrada', 'pausa_fim']:
            await interaction.response.send_message(
                "❌ Você precisa estar em expediente para iniciar uma pausa!",
                ephemeral=True
            )
            return False

        if tipo_acao == 'pausa_fim' and ultimo_registro['tipo'] != 'pausa_inicio':
            await interaction.response.send_message(
                "❌ Você precisa estar em pausa para retornar!",
                ephemeral=True
            )
            return False

        if tipo_acao == 'saida' and ultimo_registro['tipo'] not in ['entrada', 'pausa_fim']:
            await interaction.response.send_message(
                "❌ Você precisa estar em expediente para registrar saída!",
                ephemeral=True
            )
            return False

        return True

    except Exception as e:
        print(f"Erro ao verificar permissão: {e}")
        await interaction.response.send_message(
            "❌ Erro ao verificar permissão!",
            ephemeral=True
        )
        return False

@bot.event
async def on_ready():
    print(f'Bot está online como {bot.user}')

@bot.command(name='ponto')
async def ponto(ctx):
    view = PontoButtons()
    await view.update_button_states(str(ctx.author.id))

    embed = discord.Embed(
        title="Sistema de Ponto",
        description="Selecione uma opção abaixo:",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Solicitado por {ctx.author.name}")

    await ctx.send(embed=embed, view=view)

async def registrar_entrada_interaction(interaction: discord.Interaction):
    if not await verificar_permissao_acao(interaction, 'entrada'):
        return

    now = datetime.datetime.now()

    try:
        data = supabase.table('registros').insert({
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.name,
            "tipo": "entrada",
            "data_hora": now.isoformat(),
        }).execute()

        embed = discord.Embed(
            title="Registro de Entrada",
            description=f"✅ Entrada registrada às {now.strftime('%H:%M:%S')}",
            color=discord.Color.green()
        )
        embed.add_field(name="Funcionário", value=interaction.user.mention)
        embed.add_field(name="Data", value=now.strftime('%d/%m/%Y'))
        embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        print(f"Erro ao registrar entrada: {e}")
        await interaction.response.send_message("❌ Erro ao registrar entrada!", ephemeral=True)

async def registrar_pausa_inicio_interaction(interaction: discord.Interaction):
    if not await verificar_permissao_acao(interaction, 'pausa_inicio'):
        return

    now = datetime.datetime.now()

    try:
        data = supabase.table('registros').insert({
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.name,
            "tipo": "pausa_inicio",
            "data_hora": now.isoformat(),
        }).execute()

        embed = discord.Embed(
            title="Início de Pausa",
            description=f"⏸️ Pausa iniciada às {now.strftime('%H:%M:%S')}",
            color=discord.Color.yellow()
        )
        embed.add_field(name="Funcionário", value=interaction.user.mention)
        embed.add_field(name="Data", value=now.strftime('%d/%m/%Y'))
        embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        print(f"Erro ao registrar início de pausa: {e}")
        await interaction.response.send_message("❌ Erro ao registrar início de pausa!", ephemeral=True)

async def registrar_pausa_fim_interaction(interaction: discord.Interaction):
    if not await verificar_permissao_acao(interaction, 'pausa_fim'):
        return

    now = datetime.datetime.now()

    try:
        data = supabase.table('registros').insert({
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.name,
            "tipo": "pausa_fim",
            "data_hora": now.isoformat(),
        }).execute()

        embed = discord.Embed(
            title="Fim de Pausa",
            description=f"▶️ Retorno da pausa às {now.strftime('%H:%M:%S')}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Funcionário", value=interaction.user.mention)
        embed.add_field(name="Data", value=now.strftime('%d/%m/%Y'))
        embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        print(f"Erro ao registrar fim de pausa: {e}")
        await interaction.response.send_message("❌ Erro ao registrar fim de pausa!", ephemeral=True)

async def registrar_saida_interaction(interaction: discord.Interaction):
    if not await verificar_permissao_acao(interaction, 'saida'):
        return

    now = datetime.datetime.now()

    try:
        data = supabase.table('registros').insert({
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.name,
            "tipo": "saida",
            "data_hora": now.isoformat(),
        }).execute()

        embed = discord.Embed(
            title="Registro de Saída",
            description=f"✅ Saída registrada às {now.strftime('%H:%M:%S')}",
            color=discord.Color.red()
        )
        embed.add_field(name="Funcionário", value=interaction.user.mention)
        embed.add_field(name="Data", value=now.strftime('%d/%m/%Y'))
        embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        print(f"Erro ao registrar saída: {e}")
        await interaction.response.send_message("❌ Erro ao registrar saída!", ephemeral=True)

async def gerar_relatorio_interaction(interaction: discord.Interaction):
    try:
        data = supabase.table('registros')\
            .select("*")\
            .eq('user_id', str(interaction.user.id))\
            .order('data_hora', desc=True)\
            .limit(10)\
            .execute()

        if not data.data:
            await interaction.response.send_message("❌ Não há registros de ponto!", ephemeral=True)
            return

        embed = discord.Embed(
            title="Relatório de Ponto",
            description=f"Últimos 10 registros de {interaction.user.name}",
            color=discord.Color.blue()
        )

        for registro in data.data:
            data_hora = datetime.datetime.fromisoformat(registro['data_hora'].replace('Z', '+00:00'))
            tipo = registro['tipo'].replace('_', ' ').title()
            embed.add_field(
                name=f"{tipo} - {data_hora.strftime('%d/%m/%Y')}",
                value=f"Horário: {data_hora.strftime('%H:%M:%S')}",
                inline=False
            )

        embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        print(f"Erro ao gerar relatório: {e}")
        await interaction.response.send_message("❌ Erro ao gerar relatório!", ephemeral=True)

bot.run('MTMwNjM0NjUxODQ5OTgyMzc0Ng.GTaPDO.kc_b7jfA4nawSPyd-wk3dLVrVX_ear8TcX7yMY')
