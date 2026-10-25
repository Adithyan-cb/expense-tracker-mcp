from contextlib import asynccontextmanager
from typing import Annotated,Optional
from fastmcp import FastMCP
import os
import tempfile
from pydantic import Field
from sqlalchemy import select, String, Float,func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

CATEGORY_PATH = os.path.join(os.path.dirname(__file__),"categories.json")

############## DATABASE ############

DB_PATH = os.environ.get(
    "EXPENSES_DB_PATH",
    os.path.join(tempfile.gettempdir(), "expenses.db"),
)

engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}")
async_session = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(String(100))
    amount: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(100))
    subcategory: Mapped[str] = mapped_column(String(100), default="")
    note: Mapped[str] = mapped_column(String(100), default="")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date,
            "amount": self.amount,
            "category": self.category,
            "subcategory": self.subcategory,
            "note": self.note,
        }

@asynccontextmanager
async def lifespan(app: FastMCP):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

mcp = FastMCP("expense tracker", lifespan=lifespan)

################# MCP TOOLS ###############

@mcp.tool
async def add_expenses(
    date: Annotated[str, Field(description="Date in YYYY-MM-DD format")],
    amount: Annotated[float, Field(description="Amount spent", gt=0)],
    category: Annotated[str, Field(description="Main category, e.g. Food, Travel")],
    subcategory: Annotated[str, Field(description="Optional subcategory(eg:drinks,dessert,candy,icecream,etc")] = "",
    note: Annotated[str, Field(description="Optional note")] = "",
) -> dict:
    """Add a new expense entry to the database."""
    async with async_session() as session:
        expense = Expense(
            date=date,
            amount=amount,
            category=category,
            subcategory=subcategory,
            note=note,
        )
        session.add(expense)
        await session.commit()
        await session.refresh(expense)
        return expense.to_dict()


@mcp.tool
async def list_expenses() -> list[dict]:

    """List all expenses in the database."""
    async with async_session() as session:
        expenses = await session.scalars(select(Expense).order_by(Expense.id))
        return [e.to_dict() for e in expenses]


@mcp.tool
async def list_expenses_within_range(
    start_date:Annotated[str,Field(description="start date in YYYY-MM-DD")],
    end_date:Annotated[str,Field(description="end date in YYYY-MM-DD")]
)-> list[dict]:
    """list expenses within an inclusive date range"""
    async with async_session() as session:
        expenses = select(Expense).where(Expense.date.between(start_date,end_date))
        results = await session.scalars(expenses)
        return [e.to_dict() for e in results]

@mcp.tool
async def summarize(
    start_date: Annotated[str, Field(description="Start date in YYYY-MM-DD (inclusive)")],
    end_date: Annotated[str, Field(description="End date in YYYY-MM-DD (inclusive)")],
    category: Annotated[Optional[str], Field(description="Filter to a single category")] = None,
) -> list[dict]:
    """Summarize expenses by category within an inclusive date range."""
    query = (
        select(Expense.category, func.sum(Expense.amount).label("total"))
        .where(Expense.date.between(start_date, end_date))
        .group_by(Expense.category)
        .order_by(Expense.category)
    )

    if category is not None:
        query = query.where(Expense.category == category)

    async with async_session() as session:
        rows = (await session.execute(query)).all()

    return [{"category": r.category, "total": r.total} for r in rows]

@mcp.resource("expenses://categories",mime_type="application/json")
def categorise():
    with open(CATEGORY_PATH,"r",encoding="utf-8") as file:
        return file.read()



if __name__ == "__main__":
    mcp.run(transport="http",host="0.0.0.0",port=8000)
