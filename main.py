from typing import Annotated,Optional
from fastmcp import FastMCP
import os
from pydantic import Field
from sqlalchemy import create_engine, select, String, Float,func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

mcp = FastMCP("expense tracker")

CATEGORY_PATH = os.path.join(os.path.dirname(__file__),"categories.json")

############## DATABASE ############

engine = create_engine("sqlite:///expenses.db")

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

Base.metadata.create_all(engine)

################# MCP TOOLS ###############

@mcp.tool
def add_expenses(
    date: Annotated[str, Field(description="Date in YYYY-MM-DD format")],
    amount: Annotated[float, Field(description="Amount spent", gt=0)],
    category: Annotated[str, Field(description="Main category, e.g. Food, Travel")],
    subcategory: Annotated[str, Field(description="Optional subcategory(eg:drinks,dessert,candy,icecream,etc")] = "",
    note: Annotated[str, Field(description="Optional note")] = "",
) -> dict:
    """Add a new expense entry to the database."""
    with Session(engine) as session:
        expense = Expense(
            date=date,
            amount=amount,
            category=category,
            subcategory=subcategory,
            note=note,
        )
        session.add(expense)
        session.commit()
        return expense.to_dict()


@mcp.tool
def list_expenses() -> list[dict]:

    """List all expenses in the database."""
    with Session(engine) as session:
        expenses = session.scalars(select(Expense).order_by(Expense.id)).all()
        return [e.to_dict() for e in expenses]


@mcp.tool
def list_expenses_within_range(
    start_date:Annotated[str,Field(description="start date in YYYY-MM-DD")],
    end_date:Annotated[str,Field(description="end date in YYYY-MM-DD")]
)-> list[dict]:
    """list expenses within an inclusive date range"""
    with Session(engine) as session:
        expenses = select(Expense).where(Expense.date.between(start_date,end_date))
        results = session.scalars(expenses).all()
        return [e.to_dict() for e in results]

@mcp.tool
def summarize(
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

    with Session(engine) as session:
        rows = session.execute(query).all()

    return [{"category": r.category, "total": r.total} for r in rows]

@mcp.resource("expenses://categories",mime_type="application/json")
def categorise():
    with open(CATEGORY_PATH,"r",encoding="utf-8") as file:
        return file.read()



if __name__ == "__main__":
    mcp.run(transport="http",host="0.0.0.0",port=8000)
