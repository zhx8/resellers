import os
import json
import string
import random
import uuid
from datetime import datetime, timedelta
import math
import asyncio

import discord
from discord.ext import commands
from discord.ui import Button, View, Select, TextInput, Modal
from discord import SelectOption, ui
from discord import app_commands
from discord.app_commands import Choice
import os
from dotenv import load_dotenv

# --- Admin Configuration ---
ADMIN_USER_IDS = [440152099536240641]

def is_admin():
    """Custom check to see if the user is in the ADMIN_USER_IDS list."""
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id in ADMIN_USER_IDS
    return commands.check(predicate)

# --- Load Environment Variables ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Initialize bot with command prefix and intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- Database Functions ---
def load_database():
    """Load database from file or create it if it doesn't exist."""
    try:
        with open('database.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        default_data = {
    'users': {}, 
    'products': {},
    'tickets': {},
    'ticket_counter': 0,
    'ticket_category': None
}
        with open('database.json', 'w') as f:
            json.dump(default_data, f, indent=4)
        return default_data

def save_database(data):
    """Save database to file."""
    with open('database.json', 'w') as f:
        json.dump(data, f, indent=4)

# --- Helper Functions ---
def get_user_data(user_id):
    """Gets user data from the database, creating it if it doesn't exist."""
    user_id_str = str(user_id)
    if user_id_str not in database['users']:
        database['users'][user_id_str] = {
            'credits': 0,
            'discount': 0,  # 0-100, represents percentage discount
            'keys_generated': 0,
            'total_spent': 0,
            'keys': []
        }
    # Ensure all required fields exist (for backward compatibility)
    user_data = database['users'][user_id_str]
    if 'discount' not in user_data:
        user_data['discount'] = 0
    if 'keys_generated' not in user_data:
        user_data['keys_generated'] = 0
    if 'total_spent' not in user_data:
        user_data['total_spent'] = 0
    return user_data

# --- Bot Events ---
@bot.event
async def on_ready():
    """Runs when the bot has successfully connected to Discord."""
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

# --- Ticket System ---
class CreateTicketButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Create Ticket", emoji="🎫", custom_id="create_ticket")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketReasonModal())

class TicketCloseButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger, label="Close Ticket", emoji="🔒", custom_id="close_ticket")
    
    async def callback(self, interaction: discord.Interaction):
        if not any(role.name == "Admin" for role in interaction.user.roles) and interaction.user.id not in ADMIN_USER_IDS:
            await interaction.response.send_message("Only staff can close tickets.", ephemeral=True)
            return
        
        await interaction.response.send_message("Closing this ticket in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()
        
        # Remove from database
        if str(interaction.channel.id) in database['tickets']:
            del database['tickets'][str(interaction.channel.id)]
            save_database(database)

class TicketPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CreateTicketButton())

class TicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCloseButton())

class TicketReasonModal(ui.Modal, title="Create Support Ticket"):
    reason = TextInput(
        label="Reason for ticket",
        placeholder="Please describe the reason for creating this ticket...",
        style=discord.TextStyle.paragraph,
        required=True,
        min_length=10
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, self.reason.value)

async def create_ticket(interaction: discord.Interaction, reason: str):
    """Helper function to create a ticket"""
    # Defer the response to prevent "application did not respond"
    await interaction.response.defer(ephemeral=True)
    
    # Check if ticket category exists, if not create it
    ticket_category = discord.utils.get(interaction.guild.categories, id=database.get('ticket_category'))
    if not ticket_category:
        ticket_category = await interaction.guild.create_category("Tickets")
        database['ticket_category'] = ticket_category.id
        save_database(database)
    
    # Create ticket channel
    ticket_number = database.get('ticket_counter', 0) + 1
    ticket_channel = await interaction.guild.create_text_channel(
        f"ticket-{ticket_number}-{interaction.user.name}",
        category=ticket_category,
        topic=f"Ticket for {interaction.user.name} - {reason}",
        reason=f"New ticket created by {interaction.user}"
    )
    
    # Set permissions
    await ticket_channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
    await ticket_channel.set_permissions(interaction.guild.default_role, read_messages=False)
    
    # Save ticket to database
    database['tickets'][str(ticket_channel.id)] = {
        'creator_id': interaction.user.id,
        'created_at': datetime.utcnow().isoformat(),
        'status': 'open',
        'reason': reason
    }
    database['ticket_counter'] = ticket_number
    save_database(database)
    
    # Send welcome message
    embed = discord.Embed(
        title=f"🎫 Ticket #{ticket_number}",
        description=(
            f"Thank you for creating a ticket, {interaction.user.mention}!\n\n"
            "**Reseller Information**\n"
            "• Please provide the following information for faster service:\n"
            "  - Your business name (if applicable)\n"
            "  - Expected order volume\n"
            "  - Any specific requirements\n\n"
            "Our team will be with you shortly to discuss reseller pricing and setup."
        ),
        color=discord.Color.blue()
    )
    embed.add_field(name="Reason", value=reason, inline=False)
    
    # Add FAQ section
    faq_embed = discord.Embed(
        title="📋 Common Questions",
        description=(
            "**Here are answers to some common questions:**\n\n"
            "• **Reseller Pricing**: Our reseller pricing starts at 20% off retail for bulk orders.\n"
            "• **Minimum Order**: Minimum first order is $100 for reseller pricing.\n"
            "• **Payment Methods**: We accept PayPal, Bitcoin, and bank transfers.\n"
            "• **Delivery Time**: Most orders are processed within 24-48 hours.\n"
            "• **Support Hours**: Our support team is available 9AM-5PM EST, Monday-Friday.\n\n"
            "If you have any other questions, feel free to ask!"
        ),
        color=discord.Color.green()
    )
    
    embed.set_footer(text="Click the 🔒 button below to close this ticket")
    
    # Send the embeds with the view
    view = TicketView()
    # Send the first message with the main embed and view
    await ticket_channel.send(interaction.user.mention, embed=embed, view=view)
    # Send the FAQ embed as a separate message
    await ticket_channel.send(embed=faq_embed)
    
    # Send confirmation to user
    await interaction.followup.send(
        f"✅ Created your ticket: {ticket_channel.mention}",
        ephemeral=True
    )

# --- Ticket Commands ---
@bot.tree.command(name="ticketpanel", description="Create a ticket panel")
@discord.app_commands.checks.has_permissions(administrator=True)
async def ticketpanel(interaction: discord.Interaction):
    """Create a ticket panel with a button to create tickets"""
    embed = discord.Embed(
        title="🎫 Support Ticket System",
        description=(
            "**Need help or want to become a reseller?**\n\n"
            "Click the button below to create a support ticket.\n"
            "Our team will assist you with any questions about our reseller program, pricing, or any other inquiries."
        ),
        color=discord.Color.blue()
    )
    embed.set_footer(text="We typically respond within 24 hours")
    
    view = TicketPanelView()
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="ticket", description="Create a support ticket")
async def ticket(interaction: discord.Interaction, reason: str = "General Support"):
    """Create a new support ticket"""
    await create_ticket(interaction, reason)

@bot.tree.command(name="setticketcategory", description="Set the category where tickets will be created")
@discord.app_commands.checks.has_permissions(administrator=True)
async def setticketcategory(interaction: discord.Interaction):
    """Set the category where new tickets will be created"""
    database['ticket_category'] = interaction.channel.category_id
    save_database(database)
    await interaction.response.send_message(
        f"✅ Ticket category set to: {interaction.channel.category}",
        ephemeral=True
    )

@bot.tree.command(name="addtoticket", description="Add a user to the current ticket")
@discord.app_commands.checks.has_permissions(administrator=True)
async def addtoticket(interaction: discord.Interaction, user: discord.Member):
    """Add a user to the current ticket"""
    if not str(interaction.channel.id) in database['tickets']:
        await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
        return
    
    await interaction.channel.set_permissions(user, read_messages=True, send_messages=True)
    await interaction.response.send_message(f"✅ Added {user.mention} to this ticket.")

# --- Admin Commands ---
class AddKeyModal(ui.Modal, title="Add License Key"):
    def __init__(self, product_id: str, product_name: str):
        super().__init__()
        self.product_id = product_id
        self.product_name = product_name
        self.key_input = TextInput(
            label=f"Enter key(s) for {product_name}",
            style=discord.TextStyle.paragraph,
            required=True,
            min_length=5,
            placeholder="Paste one key per line to add multiple keys at once"
        )
        self.add_item(self.key_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        keys_text = self.key_input.value.strip()
        if not keys_text:
            await interaction.response.send_message("No keys provided.", ephemeral=True)
            return
        
        keys = [k.strip() for k in keys_text.split('\n') if k.strip()]
        if not keys:
            await interaction.response.send_message("No valid keys found.", ephemeral=True)
            return
        
        if self.product_id not in database['products']:
            database['products'][self.product_id] = {
                'name': self.product_name,
                'keys': []
            }
        
        if 'keys' not in database['products'][self.product_id]:
            database['products'][self.product_id]['keys'] = []
        
        added_count = 0
        for key in keys:
            if key:
                database['products'][self.product_id]['keys'].append(key)
                added_count += 1
        
        save_database(database)
        await interaction.response.send_message(
            f"✅ Added {added_count} key{'s' if added_count != 1 else ''} to {self.product_name}",
            ephemeral=True
        )

class ProductSelect(Select):
    def __init__(self, user_id=None):
        self.user_id = user_id
        options = []
        for product_id, product in database['products'].items():
            name = product.get('name', f'Product {product_id}')
            base_price = product.get('credit_cost', 0)
            
            # Calculate discounted price if user is provided
            if user_id and str(user_id) in database['users']:
                discount = database['users'][str(user_id)].get('discount', 0)
                if discount > 0:
                    discounted_price = math.ceil(base_price * (1 - discount / 100))
                    description = f"{discounted_price} credits (~~{base_price}~~)"
                else:
                    description = f"{base_price} credits"
            else:
                description = f"{base_price} credits"
                
            options.append(SelectOption(
                label=name, 
                value=product_id,
                description=description
            ))
        
        if not options:
            options.append(SelectOption(
                label="No products found",
                value="none",
                description="Create a product first using /createproduct"
            ))
        
        super().__init__(
            placeholder="Select a product to add keys to...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        product_id = self.values[0]
        if product_id == "none":
            await interaction.response.send_message(
                "No products found. Please create a product first using /createproduct",
                ephemeral=True
            )
            return
            
        product = database['products'][product_id]
        modal = AddKeyModal(product_id, product['name'])
        await interaction.response.send_modal(modal)

@bot.tree.command(name="addkey", description="Add license keys to a product")
@discord.app_commands.checks.has_permissions(administrator=True)
async def addkey(interaction: discord.Interaction):
    """Add one or more license keys to a product"""
    if not database['products']:
        await interaction.response.send_message(
            "❌ No products found. Please create a product first using /createproduct",
            ephemeral=True
        )
        return
        
    view = View()
    view.add_item(ProductSelect())
    await interaction.response.send_message(
        "Select a product to add keys to:",
        view=view,
        ephemeral=True
    )

@bot.tree.command(name="addcredits", description="Add credits to a user's balance.")
@app_commands.checks.has_permissions(administrator=True)
async def addcredits(interaction: discord.Interaction, user: discord.Member, amount: int):
    user_data = get_user_data(user.id)
    user_data['credits'] += amount
    save_database(database)
    await interaction.response.send_message(f"Added {amount} credits to {user.mention}. New balance: {user_data['credits']}", ephemeral=True)

@bot.tree.command(name="setcredits", description="Set a user's credits.")
@app_commands.checks.has_permissions(administrator=True)
async def setcredits(interaction: discord.Interaction, user: discord.Member, amount: int):
    user_data = get_user_data(user.id)
    user_data['credits'] = amount
    save_database(database)
    await interaction.response.send_message(f"Set {user.mention}'s credits to {amount}.", ephemeral=True)

@bot.tree.command(name="setdiscount", description="Set a user's discount percentage.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    user="The user to set the discount for",
    percentage="The discount percentage (0-100)"
)
async def setdiscount(interaction: discord.Interaction, user: discord.Member, percentage: int):
    """Set a user's discount percentage"""
    if not 0 <= percentage <= 100:
        await interaction.response.send_message("Discount percentage must be between 0 and 100.", ephemeral=True)
        return
    
    user_data = get_user_data(user.id)
    user_data['discount'] = percentage
    save_database(database)
    await interaction.response.send_message(f"Set {user.mention}'s discount to {percentage}%.", ephemeral=True)

# --- User Commands ---
@bot.tree.command(name="balance", description="Check your credit balance.")
async def balance(interaction: discord.Interaction):
    user_data = get_user_data(interaction.user.id)
    embed = discord.Embed(title="Your Balance", color=0x00ff00)
    embed.add_field(name="Credits", value=f"**{user_data['credits']}**", inline=True)
    embed.add_field(name="Discount", value=f"**{user_data.get('discount', 0)}%**", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="products", description="List all available products.")
async def products(interaction: discord.Interaction):
    user_data = get_user_data(interaction.user.id)
    discount = user_data.get('discount', 0)
    
    embed = discord.Embed(
        title="All Products",
        description=f"Your current discount: **{discount}%**" if discount > 0 else "",
        color=0x3498db
    )
    
    for product_id, product in database['products'].items():
        stock_count = len(product.get('keys', []))
        stock_text = f"Stock: {stock_count}"
        base_price = product['credit_cost']
        
        if discount > 0:
            discounted_price = math.ceil(base_price * (1 - discount / 100))
            price_text = f"~~{base_price}~~ **{discounted_price}** credits (You save {discount}%)"
        else:
            price_text = f"**{base_price} credits**"
        
        embed.add_field(
            name=product['name'],
            value=(
                f"ID: `{product_id}`\n"
                f"Price: {price_text}\n"
                f"{stock_text}"
            ),
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Product categories and their variants
PRODUCT_CATEGORIES = {
    "r6": ("R6 Full", {"emoji": "🎮"}),
    "fn": ("Fortnite Private", {"emoji": "🔫"}),
    "spoofer": ("Perm Spoofer", {"emoji": "🔄"})
}

PRODUCT_VARIANTS = {
    "r6": {
        "day": {"name": "1 Day", "price": 7, "duration": 1},
        "week": {"name": "1 Week", "price": 34, "duration": 7},
        "month": {"name": "1 Month", "price": 61, "duration": 30}
    },
    "fn": {
        "day": {"name": "1 Day", "price": 10, "duration": 1},
        "3day": {"name": "3 Days", "price": 19, "duration": 3},
        "week": {"name": "1 Week", "price": 34, "duration": 7},
        "month": {"name": "1 Month", "price": 55, "duration": 30},
        "life": {"name": "Lifetime", "price": 250, "duration": 9999}
    },
    "spoofer": {
        "onetime": {"name": "One Time", "price": 27, "duration": 9999},
        "life": {"name": "Lifetime", "price": 55, "duration": 9999}
    }
}

class DurationSelect(Select):
    def __init__(self, product_type: str):
        self.product_type = product_type
        # Filter products by type (r6, fn, spoofer)
        options = []
        for product_id, product in database['products'].items():
            if product_id.startswith(product_type):
                options.append(SelectOption(
                    label=product['name'],
                    description=f"{product['credit_cost']} credits",
                    value=product_id
                ))
        
        super().__init__(
            placeholder="Select a duration...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        product_id = self.values[0]
        user_data = get_user_data(interaction.user.id)
        product = database['products'][product_id]
        
        if not product.get('keys'):
            return await interaction.response.edit_message(
                content="❌ This product is out of stock.",
                view=None,
                embed=None
            )

        discount_percentage = user_data.get('discount', 0)
        discounted_cost = math.ceil(product['credit_cost'] * (1 - discount_percentage / 100))
        
        if user_data['credits'] < discounted_cost:
            return await interaction.response.edit_message(
                content=f"❌ You don't have enough credits. This costs {discounted_cost} credits.",
                view=None,
                embed=None
            )
        
        # Get a key to sell
        if not product.get('keys'):
            return await interaction.response.edit_message(
                content="❌ This product is out of stock.",
                view=None,
                embed=None
            )
        
        # Get the first key and remove it from the list
        key_to_sell = product['keys'].pop(0)
        
        # If the key contains newlines, split them and put the remaining keys back
        if '\n' in key_to_sell:
            key_lines = key_to_sell.split('\n')
            key_to_sell = key_lines[0]  # Use the first key
            remaining_keys = key_lines[1:]  # Get the rest of the keys
            if remaining_keys:  # If there are remaining keys, add them back to the product
                product['keys'].extend(remaining_keys)
        
        expiry_date = (datetime.utcnow() + timedelta(days=product['duration_days'])).strftime('%Y-%m-%d')
        
        user_data['keys'].append({
            'key': key_to_sell,
            'product': product_id,
            'purchase_date': datetime.utcnow().isoformat(),
            'expires': expiry_date
        })
        
        user_data['credits'] -= discounted_cost
        save_database(database)
        
        try:
            # Generate a unique order ID
            order_id = str(uuid.uuid4())[:8].upper()
            
            # First embed - Order Confirmation
            order_embed = discord.Embed(
                title=f"New Panel Order for {discounted_cost} credits",
                color=0x2ecc71
            )
            
            # Add order information
            order_embed.description = f"This order was made by {interaction.user.mention} | {interaction.user.name}"
            
            # Add Order ID section
            order_embed.add_field(
                name="Order ID",
                value=f"```\n{order_id}\n```",
                inline=False
            )
            
            # Add Products section
            duration_text = "Lifetime" if product['duration_days'] == 9999 else f"{product['duration_days']} Day"
            products_text = f"{product['name']}\n- {duration_text}: 1"
            order_embed.add_field(
                name="Products",
                value=f"```\n{products_text}\n```",
                inline=False
            )
            
            # Add Amount Paid section
            order_embed.add_field(
                name="Amount Paid",
                value=f"```\n{discounted_cost} credits\n```",
                inline=False
            )
            
            # Add Source section (changed from Panel to Bot)
            order_embed.add_field(
                name="Source",
                value="```\nBot\n```",
                inline=False
            )
            
            # Add user's avatar as thumbnail
            order_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            
            # Second embed - License Key
            key_embed = discord.Embed(
                title=product['name'],
                color=0x2ecc71
            )
            
            # Add Key section
            duration_text = "Lifetime" if product['duration_days'] == 9999 else f"{product['duration_days']} Day"
            key_embed.add_field(
                name=f"{duration_text} Item{'s' if product['duration_days'] != 1 else ''}",
                value=f"```\n{key_to_sell}\n```",
                inline=False
            )
            
            # Removed expiry footer as per request
                
            # Store both embeds to send
            embeds = [order_embed, key_embed]
            
            # Store order details
            if 'orders' not in database:
                database['orders'] = {}
                
            database['orders'][order_id] = {
                'user_id': str(interaction.user.id),
                'product_id': product_id,
                'product_name': product['name'],
                'key': key_to_sell,
                'price': discounted_cost,
                'date': datetime.utcnow().isoformat(),
                'expires': expiry_date
            }
            save_database(database)
            
            # Send both embeds in DM
            await interaction.user.send(embeds=embeds)
            
            # Update the interaction response
            await interaction.response.edit_message(
                content=f"✅ Order #{order_id} successful! Check your DMs for your key.",
                view=None,
                embed=None,
                delete_after=10
            )
        except discord.Forbidden:
            await interaction.response.edit_message(
                content="❌ I couldn't send you a DM. Please check your privacy settings and try again.",
                view=None,
                embed=None
            )

class VariantSelectView(View):
    def __init__(self, product_id: str):
        super().__init__()
        self.product_id = product_id
        self.add_item(VariantSelect(product_id))

class VariantSelect(Select):
    def __init__(self, product_id: str):
        self.product_id = product_id
        options = [
            SelectOption(
                label=f"{variant_info['duration']} Day{'s' if variant_info['duration'] > 1 else ''} - {variant_info['price']} credits",
                value=variant_id,
                description=f"{variant_info['duration']} days of access"
            )
            for variant_id, variant_info in PRODUCT_VARIANTS[product_id].items()
        ]
        super().__init__(
            placeholder="Select a duration...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, select_interaction: discord.Interaction):
        if select_interaction.user.id != select_interaction.message.interaction.user.id:
            await select_interaction.response.send_message("This is not your menu!", ephemeral=True)
            return
        
        # Show quantity input modal
        quantity_modal = QuantityModal(self.product_id, self.values[0])
        await select_interaction.response.send_modal(quantity_modal)

@bot.tree.command(name="gen", description="Generate a license key for a product")
@app_commands.choices(product=[
    app_commands.Choice(name=name, value=product_id)
    for product_id, (name, _) in PRODUCT_CATEGORIES.items()
])
async def gen(interaction: discord.Interaction, product: app_commands.Choice[str]):
    """Generate a license key for a product
    
    Parameters
    ----------
    product: The product to generate a key for
    """
    # Show variant selection
    view = VariantSelectView(product.value)
    await interaction.response.send_message(
        f"Select duration for {product.name}:",
        view=view,
        ephemeral=True
    )
    
    class QuantityModal(ui.Modal, title="Enter Quantity"):
        def __init__(self, product_id: str):
            super().__init__()
            self.product_id = product_id
            self.quantity = ui.TextInput(
                label="How many keys do you want to generate? (1-10)",
                placeholder="Enter a number between 1 and 10",
                min_length=1,
                max_length=2
            )
            self.add_item(self.quantity)
        
        async def on_submit(self, interaction: discord.Interaction):
            try:
                quantity = int(self.quantity.value)
                if quantity < 1 or quantity > 10:  # Max 10 keys at once
                    await interaction.response.send_message(
                        "Please enter a number between 1 and 10.",
                        ephemeral=True
                    )
                    return
                
                # Show duration selection
                view = View()
                
                class DurationButton(Button):
                    def __init__(self, label: str, variant_id: str, quantity: int):
                        super().__init__(label=label, style=discord.ButtonStyle.primary)
                        self.variant_id = variant_id
                        self.quantity = quantity
                    
                    async def callback(self, button_interaction: discord.Interaction):
                        if button_interaction.user.id != interaction.user.id:
                            await button_interaction.response.send_message("This is not your menu!", ephemeral=True)
                            return
                        
                        variant_info = PRODUCT_VARIANTS[self.view.product_id][self.variant_id]
                        product_id_full = f"{self.view.product_id}_{self.variant_id}"
                        
                        if product_id_full not in database['products'] or not database['products'][product_id_full].get('keys'):
                            await button_interaction.response.send_message("This product is out of stock.", ephemeral=True)
                            return
                        
                        await process_purchase(button_interaction, product_id_full, variant_info, self.quantity)
                
                # Add duration buttons
                for variant_id, variant_info in PRODUCT_VARIANTS[self.product_id].items():
                    duration = variant_info['duration']
                    view.add_item(DurationButton(
                        f"{duration} Day{'s' if duration > 1 else ''} - {variant_info['price']} credits", 
                        variant_id,
                        quantity
                    ))
                
                # Add back button
                class BackButton(Button):
                    def __init__(self):
                        super().__init__(label="Back", style=discord.ButtonStyle.secondary)
                    
                    async def callback(self, back_interaction: discord.Interaction):
                        if back_interaction.user.id != interaction.user.id:
                            await back_interaction.response.send_message("This is not your menu!", ephemeral=True)
                            return
                        
                        # Show product selection again
                        view = View()
                        view.add_item(ProductSelect())
                        
                        try:
                            await back_interaction.response.edit_message(
                                content="Select a product:",
                                view=view,
                                embed=None
                            )
                        except Exception as e:
                            await back_interaction.followup.send("An error occurred. Please try again.", ephemeral=True)
                            print(f"Error going back: {e}")
                
                view.add_item(BackButton())
                view.product_id = self.product_id
                
                await interaction.response.edit_message(
                    content=f"Select duration for {PRODUCT_CATEGORIES[self.product_id][0]} (Quantity: {quantity}):",
                    view=view,
                    embed=None
                )
                
            except (ValueError, AttributeError) as e:
                await interaction.response.send_message("Please enter a valid number.", ephemeral=True)
                return
    
    # Add product selection view
class QuantityModal(ui.Modal, title="Enter Quantity"):
    def __init__(self, product_id: str, variant_id: str):
        super().__init__()
        self.product_id = product_id
        self.variant_id = variant_id
        self.quantity = ui.TextInput(
            label="How many keys do you want to generate?",
            placeholder="Enter the number of keys you want",
            min_length=1,
            max_length=3
        )
        self.add_item(self.quantity)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            quantity = int(self.quantity.value)
            if quantity < 1 or quantity > 10:  # Max 10 keys at once
                await interaction.response.send_message(
                    "Please enter a number between 1 and 10.",
                    ephemeral=True
                )
                return
            
            # Process the purchase directly since we already have all the information
            variant_info = PRODUCT_VARIANTS[self.product_id][self.variant_id]
            product_id_full = f"{self.product_id}_{self.variant_id}"
            
            if product_id_full not in database['products'] or not database['products'][product_id_full].get('keys'):
                await interaction.response.send_message("This product is out of stock.", ephemeral=True)
                return
            
            await process_purchase(interaction, product_id_full, variant_info, quantity)
            
        except (ValueError, AttributeError) as e:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)
            print(f"Error in product selection: {e}")
            return

# Process purchase function
async def process_purchase(interaction: discord.Interaction, product_id: str, variant_info: dict, quantity: int = 1):
    """Process the purchase of a product"""
    # Defer the response immediately to prevent timeout
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)
    
    try:
        # Get user data and check if they have enough credits
        user_data = get_user_data(interaction.user.id)
        
        # Calculate final price with discount
        base_price = variant_info['price']
        discount_percentage = user_data.get('discount', 0)
        final_price = math.ceil(base_price * (1 - discount_percentage / 100))
        
        if user_data['credits'] < final_price:
            await interaction.followup.send(
                f"❌ You don't have enough credits. You need {final_price} credits (original: {base_price} credits)" + 
                (f" with your {discount_percentage}% discount." if discount_percentage > 0 else "."),
                ephemeral=True
            )
            return
        
        # Check if product has available keys
        if not database['products'].get(product_id, {}).get('keys'):
            await interaction.followup.send("❌ This product is currently out of stock.", ephemeral=True)
            return
        
        # Check if we have enough keys in stock
        available_keys = len(database['products'][product_id]['keys'])
        if available_keys < quantity:
            await interaction.followup.send(
                f"❌ Not enough keys in stock. Only {available_keys} available.",
                ephemeral=True
            )
            return
        
        # Calculate total price
        total_price = final_price * quantity
        
        # Check if user has enough credits
        if user_data['credits'] < total_price:
            await interaction.followup.send(
                f"❌ You don't have enough credits. You need {total_price} credits "
                f"({quantity} × {final_price} credits each)" +
                (f" with your {discount_percentage}% discount." if discount_percentage > 0 else "."),
                ephemeral=True
            )
            return
        
        # Get and remove keys from database
        keys = [database['products'][product_id]['keys'].pop(0) for _ in range(quantity)]
        
        # Update user's credits and purchase history
        user_data['credits'] -= total_price
        user_data['total_spent'] += total_price
        user_data['keys_generated'] = user_data.get('keys_generated', 0) + quantity
        
        # Add to user's keys
        if 'keys' not in user_data:
            user_data['keys'] = []
        
        # Calculate expiry date for all keys
        expiry_days = variant_info.get('duration', 1)
        expiry_date = (datetime.utcnow() + timedelta(days=expiry_days)).strftime('%Y-%m-%d %H:%M:%S')
        
        for key in keys:
            user_data['keys'].append({
                'key': key,
                'product': product_id,
                'purchase_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                'expires': expiry_date
            })
        
        save_database(database)
        
        # Create order ID (6 character alphanumeric)
        order_id = ''.join(random.choices('0123456789ABCDEF', k=8))
        
        # First embed - Order Confirmation - Yellow color (0xFFFF00)
        order_embed = discord.Embed(
            title=f"Order Confirmation - {order_id}",
            color=0xFFFF00,  # Yellow color
            timestamp=datetime.utcnow()
        )
        
        # Add user's profile picture as thumbnail
        order_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        # Add order information
        order_embed.add_field(
            name=f"This order was made by {interaction.user.mention}",
            value="",
            inline=False
        )
        
        # Add order ID
        order_embed.add_field(
            name="Order ID",
            value=f"```\n{order_id}\n```",
            inline=False
        )
        
        # Add products section with full product name
        product_name = variant_info['name']
        duration = variant_info.get('duration', 1)
        duration_text = f"{duration} Day" + ("" if duration == 1 else "s")
        
        order_embed.add_field(
            name="Products",
            value=f"```\n{product_name}\n- {duration_text}: {quantity}\n```",
            inline=False
        )
        
        # Add amount paid
        price_text = f"{final_price} credits each"
        if discount_percentage > 0:
            price_text = f"~~{base_price}~~ {final_price} credits each ({discount_percentage}% off)"
            
        order_embed.add_field(
            name="Amount Paid",
            value=f"```\n{quantity} × {price_text}\nTotal: {total_price} credits\n```",
            inline=False
        )
        
        # Add source
        order_embed.add_field(
            name="Source",
            value="```\nBot\n```",
            inline=False
        )
        
        # Create second embed for the keys
        key_embed = discord.Embed(
            title=f"{product_name} - {quantity} Key{'s' if quantity > 1 else ''}",
            color=0xFFFF00  # Yellow color
        )
        
        # Add keys information
        key_embed.description = f"```\n" + "\n\n".join(keys) + "\n```"
        
        # Store both embeds in a list
        embeds = [order_embed, key_embed]
        
        # First try to send a DM to the user
        try:
            dm_channel = await interaction.user.create_dm()
            await dm_channel.send(embeds=embeds)
            dm_success = True
            await interaction.followup.send("✅ Your purchase was successful! Check your DMs for the key.", ephemeral=True)
        except Exception as dm_error:
            print(f"Error sending DM: {dm_error}")
            dm_success = False
            # If DM fails, send in the channel
            await interaction.followup.send(
                "I couldn't send you a DM. Here's your purchase:",
                embeds=embeds,
                ephemeral=True
            )
        
        # Send public order confirmation in the ticket channel (without the keys)
        try:
            if isinstance(interaction.channel, discord.TextChannel) and 'ticket-' in interaction.channel.name:
                # Create a copy of the order embed for the public message
                public_embed = order_embed.copy()
                public_embed.title = f"Order #{order_id} - {interaction.user.display_name}'s Purchase"
                public_embed.description = f"Order completed by {interaction.user.mention}"
                
                # Add a note about where to find the keys
                if dm_success:
                    public_embed.add_field(
                        name="Key Delivery",
                        value="Your license key(s) have been sent to your DMs.",
                        inline=False
                    )
                
                await interaction.channel.send(embed=public_embed)
        except Exception as e:
            print(f"Error sending public order confirmation: {e}")
    except Exception as e:
        print(f"Unexpected error in process_purchase: {e}")
        try:
            await interaction.followup.send(
                "❌ An error occurred while processing your purchase. Please contact support.",
                ephemeral=True
            )
        except:
            # If we can't send a followup, try to send a new message
            try:
                await interaction.channel.send("❌ An error occurred. Please try again or contact support.", delete_after=10)
            except:
                pass

async def send_order_embeds(interaction: discord.Interaction, order_id: str, product_id: str, variant_info: dict,
                           key_to_sell: str, expiry_date: str, discounted_cost: int, discount_percentage: int):
    """Send order confirmation and key embeds"""
    try:
        # Defer the interaction if not already done
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=False)
        
        product_name = database['products'][product_id]['name']
        
        # First embed - Order Confirmation
        order_embed = discord.Embed(
            title=f"Order Confirmation - {order_id}",
            color=0x00ff00,  # Green color for success
            description=f"This order was made by {interaction.user.mention} | {interaction.user.name}"
        )
        
        # Add user's avatar as thumbnail to the first embed only
        order_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        # Add Order ID section
        order_embed.add_field(
            name="Order ID",
            value=f"```\n{order_id}\n```",
            inline=False
        )
        
        # Add Products section
        duration_text = "Lifetime" if variant_info['duration'] == 9999 else f"{variant_info['duration']} Day"
        products_text = f"{product_name}\n- {duration_text}: 1"
        order_embed.add_field(
            name="Products",
            value=f"```\n{products_text}\n```",
            inline=False
        )
        
        # Add Amount Paid section
        order_embed.add_field(
            name="Amount Paid",
            value=f"```\n{discounted_cost} credits\n```",
            inline=False
        )
        
        # Add Source section
        order_embed.add_field(
            name="Source",
            value="```\nBot\n```",
            inline=False
        )
        
        # Second embed - License Key (no thumbnail)
        key_embed = discord.Embed(
            title=product_name,
            color=0xffff00  # Yellow color
        )
        
        # Add Key section
        key_embed.add_field(
            name=f"{duration_text} Item{'s' if variant_info['duration'] != 1 else ''}",
            value=f"```\n{key_to_sell}\n```",
            inline=False
        )
        
        # Send both embeds in DM
        await interaction.user.send(embeds=[order_embed, key_embed])
        
        # Update the interaction response
        await interaction.followup.send(
            content=f"Order #{order_id} successful! Check your DMs for your key.",
            ephemeral=True,
            delete_after=10
        )
        
    except discord.Forbidden:
        await interaction.followup.send(
            "I couldn't send you a DM. Please check your privacy settings and try again.",
            ephemeral=True
        )
    except Exception as e:
        print(f"Error in send_order_embeds: {e}")
        await interaction.followup.send(
            "An error occurred while processing your order. Please try again.",
            ephemeral=True
        )

@bot.tree.command(name="mykeys", description="View your purchased license keys in a DM.")
async def mykeys(interaction: discord.Interaction):
    user_data = get_user_data(interaction.user.id)
    if not user_data['keys']:
        return await interaction.response.send_message("You haven't purchased any products yet.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)

    embed = discord.Embed(title="Your License Keys", color=0x9b59b6)
    
    for key_info in user_data['keys']:
        product_name = database['products'].get(key_info['product'], {}).get('name', 'Unknown Product')
        embed.add_field(
            name=product_name,
            value=f"Key: `{key_info['key']}`\nExpires: {key_info['expires']}",
            inline=False
        )
    
    try:
        await interaction.user.send(embed=embed)
        await interaction.followup.send("📨 I've sent your keys to your DMs.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ I couldn't send you a DM. Please check your privacy settings and try again.", ephemeral=True)

@bot.tree.command(name="myorders", description="View your order history")
async def myorders(interaction: discord.Interaction):
    """View your order history with order IDs and product details."""
    user_orders = []
    user_id = str(interaction.user.id)
    
    # Get all orders for this user
    if 'orders' in database:
        for order_id, order in database['orders'].items():
            if order['user_id'] == user_id:
                user_orders.append((order_id, order))
    
    if not user_orders:
        return await interaction.response.send_message(
            "You don't have any orders yet. Use `/gen` to make a purchase.",
            ephemeral=True
        )
    
    # Sort by date (newest first)
    user_orders.sort(key=lambda x: x[1]['date'], reverse=True)
    
    # Create a more compact order list
    order_list = []
    for order_id, order in user_orders:
        order_list.append(
            f"• `{order_id}` - **{order['product_name']}** "
            f"({datetime.fromisoformat(order['date']).strftime('%Y-%m-%d')}) "
            f"- Expires: `{order['expires']}`"
        )
    
    embed = discord.Embed(
        title="Your Order History",
        description="\n".join(order_list) if order_list else "No orders found.",
        color=0x9b59b6
    )
    
    embed.set_footer(text="Use /order <order_id> to view details of a specific order")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="order", description="View details of a specific order")
async def order(interaction: discord.Interaction, order_id: str):
    """View details of a specific order by ID."""
    order_id = order_id.upper()
    
    if 'orders' not in database or order_id not in database['orders']:
        return await interaction.response.send_message(
            "❌ Order not found. Please check the order ID and try again.",
            ephemeral=True
        )
    
    order_info = database['orders'][order_id]
    
    # Verify the order belongs to the user (or admin)
    if str(interaction.user.id) != order_info['user_id'] and interaction.user.id not in ADMIN_USER_IDS:
        return await interaction.response.send_message(
            "❌ You don't have permission to view this order.",
            ephemeral=True
        )
    
    # Create the order details message with inline code blocks
    key_message = f"""
    **Order ID:** `{order_id}` • **Product:** `{order_info['product_name']}`
    **Date:** `{datetime.fromisoformat(order_info['date']).strftime('%Y-%m-%d %H:%M')}`
    **Expires:** `{order_info['expires']}` • **Price:** `{order_info['price']} credits`
    
    **Key:** `{order_info['key']}`
    """
    
    embed = nextcord.Embed(
        title=f"Order #{order_id} - {order_info['product_name']}",
        description=key_message,
        color=0x2ecc71
    )
    
    if interaction.user.id in ADMIN_USER_IDS:
        user = await bot.fetch_user(int(order_info['user_id']))
        embed.set_footer(text=f"Purchased by: {user.name} (ID: {user.id})")
    else:
        embed.set_footer(text="Use /myorders to view all your purchases")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Load the database at startup
database = load_database()
                                                                                                    
# --- Run the Bot ---
if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("Error: DISCORD_TOKEN not found in .env file.")