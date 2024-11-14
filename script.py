import io
import os
import discord
from discord.ext import commands
from discord import ui
from discord import User, Member
import datetime
from realtime.types import Optional
from supabase import create_client, Client
from config import DISCORD_TOKEN, SUPABASE_URL, SUPABASE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

def converter_data_brasileira_para_iso8601(data_br: str) -> str:
    try:
        data = datetime.datetime.strptime(data_br, "%d/%m/%Y")
        return data.isoformat()
    except ValueError:
        return None

class RelatorioModal(ui.Modal, title="Gerar Relatório"):
    data_inicio = ui.TextInput(label="Data de Início (DD/MM/AAAA)", placeholder="01/01/2024")
    data_fim = ui.TextInput(label="Data de Fim (DD/MM/AAAA)", placeholder="31/12/2024")

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def is_user_manager(self, interaction: discord.Interaction) -> bool:
        member = interaction.guild.get_member(interaction.user.id)
        return member is not None and member.guild_permissions.manage_guild

    async def on_submit(self, interaction: discord.Interaction):
        data_inicio_iso = converter_data_brasileira_para_iso8601(self.data_inicio.value)
        data_fim_iso = converter_data_brasileira_para_iso8601(self.data_fim.value)

        if data_inicio_iso and data_fim_iso:
            if data_inicio_iso > data_fim_iso:
                await interaction.response.send_message("❌ A data de início não pode ser posterior à data de fim!", ephemeral=True)
                return

            await self.gerar_relatorio(interaction, data_inicio_iso, data_fim_iso)
        else:
            await interaction.response.send_message(
                "❌ Formato de data inválido! Por favor, use DD/MM/AAAA.", ephemeral=True
            )

    async def gerar_relatorio(self, interaction: discord.Interaction, data_inicio: str, data_fim: str):
        user_id = str(interaction.user.id)

        registros = supabase.table('registros')\
            .select('*')\
            .eq('user_id', user_id)\
            .gte('data_hora', data_inicio)\
            .lte('data_hora', data_fim)\
            .order('data_hora', desc=True)\
            .execute()

        if not registros.data:
            await interaction.response.send_message("❌ Não há registros para o intervalo selecionado.", ephemeral=True)
            return

        total_horas_trabalhadas = datetime.timedelta()
        total_pausa = datetime.timedelta()

        ultima_entrada = None
        ultima_pausa_inicio = None

        for registro in registros.data:
            tipo = registro['tipo']
            data_hora = datetime.datetime.fromisoformat(registro['data_hora'])

            if tipo == "entrada":
                ultima_entrada = data_hora
            elif tipo == "saida" and ultima_entrada:
                total_horas_trabalhadas += data_hora - ultima_entrada
                ultima_entrada = None
            elif tipo == "pausa_inicio":
                ultima_pausa_inicio = data_hora
            elif tipo == "pausa_fim" and ultima_pausa_inicio:
                total_pausa += data_hora - ultima_pausa_inicio
                ultima_pausa_inicio = None

        horas_trabalhadas_excluindo_pausa = total_horas_trabalhadas - total_pausa

        horas_trabalhadas_str = str(horas_trabalhadas_excluindo_pausa)
        pausa_str = str(total_pausa)

        embed = discord.Embed(
            title="Relatório de Horas Trabalhadas e Pausas",
            description=f"Relatório do período de {data_inicio} a {data_fim}",
            color=discord.Color.green()
        )

        embed.add_field(name="Horas Trabalhadas (sem pausas)", value=horas_trabalhadas_str, inline=False)
        embed.add_field(name="Total de Pausas", value=pausa_str, inline=False)

        await interaction.response.send_message(embed=embed)

class PontoButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.message: Optional[discord.Message] = None
        self.eventos_trilha = []
        self.bot = bot

    async def is_user_manager(self, interaction: discord.Interaction) -> bool:
        member = interaction.guild.get_member(interaction.user.id)
        return member is not None and member.guild_permissions.manage_guild

    async def adicionar_evento_trilha(self, evento: str, usuario: User, tipo: str):
        timestamp = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        cor_badge = {
            'entrada': discord.Color.green(),
            'pausa_inicio': discord.Color.blurple(),
            'pausa_fim': discord.Color.blurple(),
            'saida': discord.Color.red(),
        }.get(tipo, discord.Color.default())

        badge = f"**[{timestamp}]** {evento} - {usuario.name}"
        self.eventos_trilha.append((badge, cor_badge))

        trilha_texto = "\n".join([f"{badge}" for badge, _ in self.eventos_trilha])

        if self.message:
            # Criação da embed com o avatar do usuário
            embed = discord.Embed(
                title="Histórico de Ponto",
                description=trilha_texto,
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=usuario.avatar.url + "?size=128")  # Mantém o avatar
            await self.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Registrar Entrada", style=discord.ButtonStyle.green, custom_id="entrada")
    async def entrada_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.adicionar_evento_trilha("Entrada registrada", interaction.user, 'entrada')
        await interaction.response.send_message("✅ Entrada registrada!", ephemeral=True)
        self.entrada_button.disabled = True  # Desabilita o botão de entrada
        self.pausa_inicio_button.disabled = False  # Habilita o botão de pausa
        self.saida_button.disabled = False  # Habilita o botão de saída
        await self.message.edit(view=self)

    @discord.ui.button(label="Iniciar Pausa", style=discord.ButtonStyle.blurple, custom_id="pausa_inicio", disabled=True)
    async def pausa_inicio_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.adicionar_evento_trilha("Pausa iniciada", interaction.user, 'pausa_inicio')
        await interaction.response.send_message("✅ Pausa iniciada!", ephemeral=True)
        self.pausa_inicio_button.disabled = True  # Desabilita o botão de iniciar pausa
        self.pausa_fim_button.disabled = False  # Habilita o botão de voltar da pausa
        await self.message.edit(view=self)

    @discord.ui.button(label="Retornar da Pausa", style=discord.ButtonStyle.blurple, custom_id="pausa_fim", disabled=True)
    async def pausa_fim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.adicionar_evento_trilha("Pausa finalizada", interaction.user, 'pausa_fim')
        await interaction.response.send_message("✅ Pausa finalizada!", ephemeral=True)
        self.pausa_fim_button.disabled = True  # Desabilita o botão de retornar da pausa
        self.pausa_inicio_button.disabled = False  # Reabilita o botão de iniciar pausa
        self.saida_button.disabled = False  # Habilita o botão de saída
        await self.message.edit(view=self)

    @discord.ui.button(label="Encerrar Expediente", style=discord.ButtonStyle.red, custom_id="saida", disabled=True)
    async def saida_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Registra a saída
        await self.adicionar_evento_trilha("Saída registrada", interaction.user, 'saida')

        # Mensagem de confirmação
        await interaction.response.send_message("✅ Saída registrada! Expediente finalizado.", ephemeral=True)

        # Desabilita todos os botões, exceto o de "Relatório"
        self.entrada_button.disabled = True
        self.pausa_inicio_button.disabled = True
        self.pausa_fim_button.disabled = True
        self.saida_button.disabled = True
        self.relatorio_button.disabled = False  # Habilita o botão de relatório

        # Atualiza a view
        await self.message.edit(view=self)

    @discord.ui.button(label="Ver Relatório", style=discord.ButtonStyle.grey, custom_id="relatorio")
    async def relatorio_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verifica se o usuário é um administrador
        if not await self.is_user_manager(interaction):
            await interaction.response.send_message("❌ Você não tem permissão para gerar o relatório. Somente administradores podem fazer isso.", ephemeral=True)
            return

        # Envia o modal
        await interaction.response.send_modal(RelatorioModal(self.bot))

async def verificar_usuario_ponto(user_id: str) -> bool:
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
                "❌ Você precisa estar em expediente para iniciar uma pausa.",
                ephemeral=True
            )
            return False

        if tipo_acao == 'pausa_fim' and ultimo_registro['tipo'] != 'pausa_inicio':
            await interaction.response.send_message(
                "❌ Você não pode finalizar uma pausa que não foi iniciada.",
                ephemeral=True
            )
            return False

        if tipo_acao == 'saida' and ultimo_registro['tipo'] != 'entrada':
            await interaction.response.send_message(
                "❌ Você não pode registrar a saída sem ter uma entrada.",
                ephemeral=True
            )
            return False

        return True
    except Exception as e:
        print(f"Erro ao verificar permissão: {e}")
        return False

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")

@bot.command()
async def ponto(ctx):
    user_id = str(ctx.author.id)
    view = PontoButtons()

    embed = discord.Embed(
        title="Escolha a opção que deseja registrar o ponto:",
        description="Selecione a ação para registrar seu ponto.",
        color=discord.Color.blue()
    )

    embed.set_thumbnail(url=ctx.author.avatar.url + "?size=128")

    # Verifica se o usuário pode registrar ponto
    if await verificar_usuario_ponto(user_id):
        if not view.message:  # Verifica se a mensagem ainda não foi enviada
            view.message = await ctx.send(embed=embed, view=view)
        else:
            await view.message.edit(embed=embed, view=view)  # Edita a mensagem existente com a view
    else:
        await ctx.send("Você já tem um ponto registrado. Você não pode registrar outro ponto até encerrar o expediente.")

@bot.command()
async def relatorio(ctx):
    if not await verificar_permissao_acao(ctx, 'relatorio'):
        return

    await ctx.send_modal(RelatorioModal(bot))

bot.run(DISCORD_TOKEN)
