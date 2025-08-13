from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversations",
        sa.Column("conversation_id", sa.String(), primary_key=True),
        sa.Column(
            "type", sa.Enum("direct", "group", name="conversation_type"), nullable=False
        ),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("tenant_id", sa.String(), index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_seq", sa.BigInteger(), server_default="0"),
    )

    op.create_table(
        "conversation_members",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(),
            sa.ForeignKey("conversations.conversation_id"),
            index=True,
        ),
        sa.Column("user_id", sa.String(), index=True),
        sa.Column(
            "role",
            sa.Enum("owner", "member", "assistant", name="conversation_member_role"),
            nullable=False,
        ),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.Column("last_read_message_id", sa.String(), nullable=True),
        sa.Column("muted", sa.Boolean(), server_default="0"),
        sa.Column("tenant_id", sa.String(), index=True),
    )

    op.create_table(
        "im_messages",
        sa.Column("message_id", sa.String(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(),
            sa.ForeignKey("conversations.conversation_id"),
            index=True,
        ),
        sa.Column("sender_id", sa.String(), index=True),
        sa.Column(
            "type",
            sa.Enum(
                "text",
                "image",
                "file",
                "audio",
                "video",
                "system",
                "ai",
                "stream_chunk",
                name="message_type",
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("reply_to", sa.String(), nullable=True),
        sa.Column("client_msg_id", sa.String(), index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("seq", sa.BigInteger(), index=True),
        sa.Column("edited_at", sa.DateTime(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("sent", "delivered", "read", name="message_status"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(), index=True),
    )

    op.create_index("idx_messages_conv_seq", "im_messages", ["conversation_id", "seq"])
    op.create_index(
        "idx_messages_sender_created", "im_messages", ["sender_id", "created_at"]
    )


def downgrade():
    op.drop_index("idx_messages_sender_created", table_name="im_messages")
    op.drop_index("idx_messages_conv_seq", table_name="im_messages")
    op.drop_table("im_messages")
    op.drop_table("conversation_members")
    op.drop_table("conversations")
