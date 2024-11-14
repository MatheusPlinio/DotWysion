import io
import os
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

def converter_data_brasileira_para_iso8601(data_br: str) -> str:
    try:
        # Tenta converter a string de data brasileira para um objeto datetime
        data = datetime.datetime.strptime(data_br, "%d/%m/%Y")
        return data.isoformat()  # Retorna a data no formato ISO 8601
    except ValueError:
        return None

class RelatorioModal(ui.Modal, title="Gerar Relatório"):
    data_inicio = ui.TextInput(label="Data de Início (DD/MM/AAAA)", placeholder="01/01/2024")
    data_fim = ui.TextInput(label="Data de Fim (DD/MM/AAAA)", placeholder="31/12/2024")

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        data_inicio_iso = converter_data_brasileira_para_iso8601(self.data_inicio.value)
        data_fim_iso = converter_data_brasileira_para_iso8601(self.data_fim.value)

        # Valida se as datas são válidas e se a data de início é anterior à data de fim
        if data_inicio_iso and data_fim_iso:
            if data_inicio_iso > data_fim_iso:
                await interaction.response.send_message("❌ A data de início não pode ser posterior à data de fim!", ephemeral=True)
                return

            # Gerar o relatório com base nas datas informadas
            await self.gerar_relatorio(interaction, data_inicio_iso, data_fim_iso)
        else:
            await interaction.response.send_message(
                "❌ Formato de data inválido! Por favor, use DD/MM/AAAA.", ephemeral=True
            )

    async def gerar_relatorio(self, interaction: discord.Interaction, data_inicio: str, data_fim: str):
        user_id = str(interaction.user.id)

        # Filtrar registros pelo intervalo de datas
        registros = supabase.table('registros')\
            .select('*')\
            .eq('user_id', user_id)\
            .gte('data_hora', data_inicio)\
            .lte('data_hora', data_fim)\
            .order('data_hora', desc=True)\
            .execute()

        # Verificar se há registros
        if not registros.data:
            await interaction.response.send_message("❌ Não há registros para o intervalo selecionado.", ephemeral=True)
            return

        total_horas_trabalhadas = datetime.timedelta()  # Para somar as horas trabalhadas
        total_pausa = datetime.timedelta()  # Para somar o tempo de pausa

        ultima_entrada = None
        ultima_pausa_inicio = None

        for registro in registros.data:
            tipo = registro['tipo']
            data_hora = datetime.datetime.fromisoformat(registro['data_hora'])

            if tipo == "entrada":
                ultima_entrada = data_hora
            elif tipo == "saida" and ultima_entrada:
                # Se temos uma entrada e uma saída, calculamos as horas trabalhadas
                total_horas_trabalhadas += data_hora - ultima_entrada
                ultima_entrada = None  # Resetar entrada após a saída
            elif tipo == "pausa_inicio":
                ultima_pausa_inicio = data_hora
            elif tipo == "pausa_fim" and ultima_pausa_inicio:
                # Se temos uma pausa de início e fim, calculamos a pausa
                total_pausa += data_hora - ultima_pausa_inicio
                ultima_pausa_inicio = None  # Resetar pausa após a pausa_fim

        # Calculando o total de horas trabalhadas excluindo pausas
        horas_trabalhadas_excluindo_pausa = total_horas_trabalhadas - total_pausa

        # Formatando as durações em formato legível
        horas_trabalhadas_str = str(horas_trabalhadas_excluindo_pausa)
        pausa_str = str(total_pausa)

        # Montando o conteúdo do relatório
        embed = discord.Embed(
            title="Relatório de Horas Trabalhadas e Pausas",
            description=f"Relatório do período de {data_inicio} a {data_fim}",
            color=discord.Color.green()
        )

        embed.add_field(name="Horas Trabalhadas (sem pausas)", value=horas_trabalhadas_str, inline=False)
        embed.add_field(name="Total de Pausas", value=pausa_str, inline=False)

        # Enviar o relatório para o usuário
        await interaction.response.send_message(embed=embed)

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

    @discord.ui.button(label="Ver Relatório", style=discord.ButtonStyle.grey, custom_id="relatorio")
    async def relatorio_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Gerar CSV com os registros do usuário
        await interaction.response.send_modal(RelatorioModal(bot))

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
        embed.add_field(name="Data", value=now.strftime("%d/%m/%Y"))
        embed.add_field(name="Hora", value=now.strftime("%H:%M"))

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao registrar entrada: {e}", ephemeral=True)

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
            title="Pausa Iniciada",
            description=f"✅ Pausa iniciada às {now.strftime('%H:%M:%S')}",
            color=discord.Color.orange()
        )
        embed.add_field(name="Funcionário", value=interaction.user.mention)
        embed.add_field(name="Data", value=now.strftime("%d/%m/%Y"))
        embed.add_field(name="Hora", value=now.strftime("%H:%M"))

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao iniciar pausa: {e}", ephemeral=True)

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
            title="Pausa Finalizada",
            description=f"✅ Pausa finalizada às {now.strftime('%H:%M:%S')}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Funcionário", value=interaction.user.mention)
        embed.add_field(name="Data", value=now.strftime("%d/%m/%Y"))
        embed.add_field(name="Hora", value=now.strftime("%H:%M"))

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao finalizar pausa: {e}", ephemeral=True)

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
        embed.add_field(name="Data", value=now.strftime("%d/%m/%Y"))
        embed.add_field(name="Hora", value=now.strftime("%H:%M"))

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao registrar saída: {e}", ephemeral=True)

bot.run(DISCORD_TOKEN)
